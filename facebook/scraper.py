import re
from typing import List, Dict
from playwright.async_api import Page
from facebook.database import fb_add_targets_bulk, fb_is_already_targeted, fb_log_action, fb_log_error
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)
FB_URL = "https://www.facebook.com"

_SKIP_PATHS = {
    "pages", "groups", "events", "watch", "marketplace", "gaming", "hashtag",
    "ads", "help", "privacy", "login", "checkpoint", "recover", "settings",
    "notifications", "messages", "bookmarks", "search", "explore", "share",
    "photos", "videos", "reels", "about", "community", "home", "likes",
    "followers", "following", "friends", "mentions", "tagged", "reel",
}

_JS_EXTRACT = """
() => {
    const results = [];
    const seen = new Set();
    document.querySelectorAll('a[href]').forEach(a => {
        try {
            let href = a.href || '';
            if (!href.includes('facebook.com')) return;
            const url = new URL(href);
            if (url.hostname !== 'www.facebook.com') return;
            let path = url.pathname.replace(/\\/+$/, '');
            if (path === '/profile.php') {
                const id = url.searchParams.get('id');
                if (!id) return;
                const canonical = 'https://www.facebook.com/profile.php?id=' + id;
                if (!seen.has(canonical)) {
                    seen.add(canonical);
                    results.push({ url: canonical, name: (a.innerText || a.getAttribute('aria-label') || '').trim().substring(0, 60) });
                }
                return;
            }
            const parts = path.split('/').filter(Boolean);
            if (parts.length !== 1) return;
            const slug = parts[0].toLowerCase();
            const skip = ['pages','groups','events','watch','marketplace','gaming','hashtag',
                          'ads','help','privacy','login','checkpoint','recover','settings',
                          'notifications','messages','bookmarks','search','explore','share',
                          'photos','videos','reels','about','community','home','likes',
                          'followers','following','friends','mentions','tagged','reel','story'];
            if (skip.includes(slug)) return;
            if (!/^[\\w.]{3,60}$/.test(parts[0])) return;
            const canonical = 'https://www.facebook.com/' + parts[0];
            if (!seen.has(canonical)) {
                seen.add(canonical);
                results.push({ url: canonical, name: (a.innerText || a.getAttribute('aria-label') || '').trim().substring(0, 60) });
            }
        } catch(e) {}
    });
    return results;
}
"""

_JS_CLICK_MORE_COMMENTS = """
() => {
    let clicked = 0;
    document.querySelectorAll('[role="button"], button').forEach(el => {
        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
        if (
            txt.includes('view') || txt.includes('more comment') ||
            txt.includes('voir') || txt.includes('commentaire') ||
            txt.includes('afficher') || txt.includes('réponse') ||
            txt.includes('reply') || txt.includes('replies') ||
            txt.includes('تعليق') || txt.includes('المزيد')
        ) {
            try { el.click(); clicked++; } catch(e) {}
        }
    });
    return clicked;
}
"""


class FbTargetScraper:
    def __init__(self, page: Page):
        self.page = page

    async def scrape_friends_of_friend(self, friend_id: str, limit: int = 200) -> List[Dict]:
        url = f"{FB_URL}/{friend_id.lstrip('/')}/friends"
        logger.info(f"[FB] Scraping amis de {friend_id}...")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 4)
            if "login" in self.page.url or "checkpoint" in self.page.url:
                logger.warning("[FB] Non connecté pour scraping amis")
                return []
            content = await self.page.content()
            if "privée" in content.lower() or "private" in content.lower():
                fb_log_action("scrape_friends", target=friend_id, status="error", details="liste privée")
                return []
            targets = await self._js_collect(limit)
            return await self._save(targets, f"friends_of:{friend_id}", "scrape_friends", friend_id)
        except Exception as e:
            logger.warning(f"[FB] Erreur scraping amis : {e}")
            fb_log_error("scrape_error", str(e), "scrape_friends")
            return []

    async def scrape_page_likers(self, page_id: str, limit: int = 200) -> List[Dict]:
        logger.info(f"[FB] Scraping commentateurs de {page_id}...")
        try:
            await self.page.goto(f"{FB_URL}/{page_id}", wait_until="domcontentloaded", timeout=30000)
            await random_sleep(3, 5)

            real_url = self.page.url
            if "login" in real_url or "checkpoint" in real_url:
                logger.warning(f"[FB] Non connecté lors du scraping de {page_id}")
                fb_log_action("scrape_page", target=page_id, status="error", details="non connecté")
                return []

            all_targets: List[Dict] = []

            # Scroll sur la page principale pour charger les posts
            for i in range(5):
                await self.page.evaluate("window.scrollBy(0, 800)")
                await random_sleep(1.5, 2.5)
                batch = await self._js_collect(limit)
                for t in batch:
                    if not any(x["profile_url"] == t["profile_url"] for x in all_targets):
                        all_targets.append(t)
                if len(all_targets) >= limit:
                    break

            logger.info(f"[FB] {len(all_targets)} profils sur la page principale")

            # Aller dans les posts individuels pour charger les commentaires
            post_urls = await self._find_post_urls(12)
            logger.info(f"[FB] {len(post_urls)} posts à explorer")

            for post_url in post_urls:
                if len(all_targets) >= limit:
                    break
                batch = await self._scrape_post_comments(post_url, limit - len(all_targets))
                logger.info(f"[FB] {len(batch)} profils dans ce post")
                for t in batch:
                    if not any(x["profile_url"] == t["profile_url"] for x in all_targets):
                        all_targets.append(t)

            return await self._save(all_targets, f"page:{page_id}", "scrape_page", page_id)

        except Exception as e:
            logger.warning(f"[FB] Erreur scraping page : {e}")
            fb_log_error("scrape_page_error", str(e), "scrape_page")
            return []

    async def _scrape_post_comments(self, post_url: str, limit: int) -> List[Dict]:
        """Navigue dans un post et charge les commentaires via clics + scroll."""
        try:
            await self.page.goto(post_url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 3)

            # Scroll vers le bas pour atteindre les commentaires
            for _ in range(4):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await random_sleep(0.8, 1.5)

            # Cliquer plusieurs fois pour charger plus de commentaires
            for _ in range(5):
                clicked = await self.page.evaluate(_JS_CLICK_MORE_COMMENTS)
                await random_sleep(1.2, 2.0)
                await self.page.evaluate("window.scrollBy(0, 500)")
                await random_sleep(0.8, 1.2)
                if clicked == 0:
                    break

            # Scroll final pour s'assurer que tout est chargé
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await random_sleep(0.5, 1.0)

            return await self._js_collect(limit)
        except Exception as e:
            logger.warning(f"[FB] Erreur post {post_url} : {e}")
            return []

    async def _find_post_urls(self, max_posts: int = 12) -> List[str]:
        links, seen = [], set()
        els = await self.page.query_selector_all("a[href]")
        for el in els:
            raw = (await el.get_attribute("href") or "").strip()
            if any(k in raw for k in ("/posts/", "/permalink/", "/videos/", "story_fbid", "story.php", "/photo/", "pfbid")):
                if raw not in seen:
                    seen.add(raw)
                    if raw.startswith("/"):
                        raw = FB_URL + raw
                    links.append(raw)
            if len(links) >= max_posts:
                break
        return links

    async def _js_collect(self, limit: int) -> List[Dict]:
        try:
            raw = await self.page.evaluate(_JS_EXTRACT)
            results = []
            for item in raw[:limit]:
                url  = item.get("url", "")
                name = (item.get("name", "") or "").strip()
                if url and name and len(name) > 1:
                    results.append({"profile_url": url, "name": name})
            return results
        except Exception as e:
            logger.warning(f"[FB] JS extract échoué : {e}")
            return []

    async def _save(self, targets: List[Dict], source: str, action: str, target_id: str) -> List[Dict]:
        new = [t for t in targets if not fb_is_already_targeted(t["profile_url"])]
        added = 0
        if new:
            added = fb_add_targets_bulk(new, source=source)
            logger.info(f"[FB] {added} nouveaux profils ajoutés depuis {target_id}")
        fb_log_action(action, target=target_id, status="success", details=f"{added} ajoutés")
        return new

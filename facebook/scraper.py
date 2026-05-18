import re
from typing import List, Dict
from playwright.async_api import Page
from facebook.database import fb_add_targets_bulk, fb_is_already_targeted, fb_log_action, fb_log_error
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)

FB_URL = "https://www.facebook.com"
MBASIC  = "https://mbasic.facebook.com"

_SKIP = {
    "pages", "groups", "events", "watch", "marketplace", "gaming", "hashtag",
    "ads", "help", "privacy", "login", "checkpoint", "recover", "settings",
    "notifications", "messages", "bookmarks", "search", "explore", "share",
    "photos", "videos", "reels", "about", "community", "home", "likes",
    "followers", "following", "friends", "mentions", "tagged",
}


def _normalize(href: str) -> str:
    if not href:
        return ""
    # Garder la query pour profile.php?id=
    if "profile.php" in href:
        base = href.split("&")[0]          # garder id= seulement
        if not base.startswith("http"):
            base = "https://www.facebook.com" + base
        return base.replace("mbasic.facebook.com", "www.facebook.com")
    href = href.split("?")[0].rstrip("/")
    if href.startswith("/"):
        href = "https://www.facebook.com" + href
    return href.replace("mbasic.facebook.com", "www.facebook.com")


def _is_profile(url: str) -> bool:
    if not url.startswith("https://www.facebook.com/"):
        return False
    path = url[len("https://www.facebook.com/"):].strip("/")
    if not path:
        return False
    # profile.php?id=XXXXXXXX
    if path.startswith("profile.php"):
        return "id=" in path
    # Pas de slash dans le chemin = profil direct /username
    if "/" in path:
        return False
    # Ignorer les slugs réservés
    if path.lower() in _SKIP:
        return False
    # Doit contenir des caractères valides (username FB)
    return bool(re.match(r'^[\w.]{3,60}$', path))


class FbTargetScraper:
    def __init__(self, page: Page):
        self.page = page

    async def scrape_friends_of_friend(self, friend_id: str, limit: int = 200) -> List[Dict]:
        url = f"{MBASIC}/{friend_id.lstrip('/')}/friends"
        logger.info(f"[FB] Scraping amis de {friend_id}...")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 4)
            if "login" in self.page.url:
                logger.warning("[FB] Redirigé vers login")
                return []
            content = await self.page.content()
            if "privée" in content.lower() or "private" in content.lower():
                fb_log_action("scrape_friends", target=friend_id, status="error", details="liste privée")
                return []
            targets = await self._collect_profiles(limit)
            return await self._save(targets, f"friends_of:{friend_id}", "scrape_friends", friend_id)
        except Exception as e:
            logger.warning(f"[FB] Erreur scraping amis : {e}")
            fb_log_error("scrape_error", str(e), "scrape_friends")
            return []

    async def scrape_page_likers(self, page_id: str, limit: int = 200) -> List[Dict]:
        """
        Scrape les profils depuis une page Facebook via mbasic.
        Stratégie : scroll sur la page principale pour collecter les commentateurs
        visibles inline, puis aller dans les posts individuels si nécessaire.
        """
        logger.info(f"[FB] Scraping profils de la page {page_id}...")
        try:
            # 1. Charger la page principale et scroll
            page_url = f"{MBASIC}/{page_id}"
            await self.page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
            await random_sleep(2, 4)

            real_url = self.page.url
            logger.info(f"[FB] URL réelle : {real_url}")

            if "login" in real_url or "checkpoint" in real_url:
                logger.warning("[FB] Non connecté — cookies invalides ?")
                fb_log_action("scrape_page", target=page_id, status="error", details="non connecté")
                return []

            # Scroll pour charger plus de contenu inline
            all_targets: List[Dict] = []
            for scroll_round in range(6):
                await self.page.evaluate("window.scrollBy(0, 800)")
                await random_sleep(1.5, 2.5)

                batch = await self._collect_profiles(limit)
                for t in batch:
                    if t not in all_targets:
                        all_targets.append(t)

                if len(all_targets) >= limit:
                    break

            logger.info(f"[FB] {len(all_targets)} profils trouvés sur la page principale")

            # 2. Si pas assez, aller dans les posts individuels
            if len(all_targets) < 20:
                post_urls = await self._find_post_urls_on_current_page(8)
                logger.info(f"[FB] {len(post_urls)} posts à explorer")

                per_post = max((limit - len(all_targets)) // max(len(post_urls), 1), 15)
                for post_url in post_urls:
                    if len(all_targets) >= limit:
                        break
                    await self.page.goto(post_url, wait_until="domcontentloaded", timeout=25000)
                    await random_sleep(2, 3)
                    logger.info(f"[FB] Post : {self.page.url[:80]}")
                    batch = await self._collect_profiles(per_post)
                    logger.info(f"[FB] {len(batch)} profils dans ce post")
                    for t in batch:
                        if t not in all_targets:
                            all_targets.append(t)
                    await random_sleep(1.5, 3)

            return await self._save(all_targets, f"page:{page_id}", "scrape_page", page_id)

        except Exception as e:
            logger.warning(f"[FB] Erreur scraping page : {e}")
            fb_log_error("scrape_page_error", str(e), "scrape_page")
            return []

    async def _find_post_urls_on_current_page(self, max_posts: int = 8) -> List[str]:
        """Trouve les liens de posts sur la page courante."""
        links, seen = [], set()
        els = await self.page.query_selector_all("a[href]")

        # Log des 10 premiers liens pour debug
        sample = []
        for el in els[:30]:
            h = (await el.get_attribute("href") or "").strip()
            if h:
                sample.append(h)
        logger.info(f"[FB] Échantillon liens : {sample[:10]}")

        for el in els:
            raw = (await el.get_attribute("href") or "").strip()
            if not raw:
                continue
            # Détection flexible : tout lien avec un long identifiant numérique
            has_post_id = bool(re.search(r'/\d{8,}', raw))
            has_keyword = any(k in raw for k in ("story.php", "/posts/", "/permalink/", "story_fbid", "/videos/"))
            if (has_post_id or has_keyword) and raw not in seen:
                # Construire l'URL mbasic complète
                if raw.startswith("/"):
                    url = MBASIC + raw
                elif raw.startswith("http"):
                    url = raw.replace("www.facebook.com", "mbasic.facebook.com")
                else:
                    continue
                seen.add(raw)
                links.append(url)
            if len(links) >= max_posts:
                break
        return links

    async def _collect_profiles(self, limit: int) -> List[Dict]:
        """Collecte les liens de profils Facebook sur la page courante."""
        targets, seen = [], set()
        els = await self.page.query_selector_all("a[href]")

        for el in els:
            try:
                raw  = (await el.get_attribute("href") or "").strip()
                name = (await el.inner_text() or "").strip()[:60]
                if not raw or not name or len(name) < 2:
                    continue
                url = _normalize(raw)
                if not url or url in seen:
                    continue
                if _is_profile(url):
                    seen.add(url)
                    targets.append({"profile_url": url, "name": name})
            except Exception:
                continue
            if len(targets) >= limit:
                break
        return targets

    async def _save(self, targets: List[Dict], source: str, action: str, target_id: str) -> List[Dict]:
        new = [t for t in targets if not fb_is_already_targeted(t["profile_url"])]
        added = 0
        if new:
            added = fb_add_targets_bulk(new, source=source)
            logger.info(f"[FB] {added} nouveaux profils ajoutés depuis {target_id}")
        fb_log_action(action, target=target_id, status="success", details=f"{added} ajoutés")
        return new

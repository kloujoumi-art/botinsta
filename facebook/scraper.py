import random
from typing import List, Dict
from playwright.async_api import Page
from facebook.database import fb_add_targets_bulk, fb_is_already_targeted, fb_log_action, fb_log_error
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)
FB_URL = "https://www.facebook.com"

# Sélecteurs pour trouver les liens de profils dans les commentaires
COMMENT_PROFILE_SELECTORS = [
    'div[role="article"] a[href*="facebook.com/"][aria-label]',
    'div[data-testid="comment"] a[href*="facebook.com/"]',
    'ul[data-testid="comments-list"] a[href*="facebook.com/"]',
    'div[aria-label*="ommentaire"] a[href*="facebook.com/"]',
    'div[class*="comment"] a[href*="facebook.com/"]',
]

# Sélecteurs pour trouver les liens de posts sur une page
POST_LINK_SELECTORS = [
    'a[href*="/posts/"]',
    'a[href*="/permalink/"]',
    'a[href*="/videos/"]',
    'a[href*="/photos/"]',
    'a[role="link"][href*="facebook.com"]',
]


class FbTargetScraper:
    def __init__(self, page: Page):
        self.page = page

    async def scrape_friends_of_friend(self, friend_id: str, limit: int = 200) -> List[Dict]:
        url = friend_id if friend_id.startswith("http") else f"{FB_URL}/{friend_id}"
        url = url.rstrip("/") + "/friends"
        logger.info(f"[FB] Scraping amis de {friend_id}...")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(3, 5)
            if "login" in self.page.url:
                return []
            content = await self.page.content()
            if "privée" in content.lower() or "private" in content.lower():
                fb_log_action("scrape_friends", target=friend_id, status="error", details="liste privée")
                return []
            targets = await self._scroll_and_collect(limit)
            new = [t for t in targets if not fb_is_already_targeted(t["profile_url"])]
            if new:
                added = fb_add_targets_bulk(new, source=f"friends_of:{friend_id}")
                logger.info(f"[FB] {added} amis de {friend_id} ajoutés")
            fb_log_action("scrape_friends", target=friend_id, status="success", details=f"{len(new)} ajoutés")
            return new
        except Exception as e:
            logger.warning(f"[FB] Erreur scraping amis : {e}")
            fb_log_error("scrape_error", str(e), "scrape_friends")
            return []

    async def scrape_page_likers(self, page_id: str, limit: int = 200) -> List[Dict]:
        """Scrape les commentateurs des posts d'une page (plus fiable que les likers)."""
        url = page_id if page_id.startswith("http") else f"{FB_URL}/{page_id}"
        logger.info(f"[FB] Scraping commentateurs de la page {page_id}...")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await random_sleep(3, 5)
            if "login" in self.page.url or "checkpoint" in self.page.url:
                logger.warning(f"[FB] Non connecté lors du scraping de {page_id}")
                return []

            post_links = await self._get_post_links(limit=8)
            logger.info(f"[FB] {len(post_links)} posts trouvés sur {page_id}")

            if not post_links:
                # Essayer de scraper les profils directement depuis la page
                targets = await self._collect_profiles_from_page(limit)
                new = [t for t in targets if not fb_is_already_targeted(t["profile_url"])]
                if new:
                    added = fb_add_targets_bulk(new, source=f"page:{page_id}")
                    logger.info(f"[FB] {added} profils de {page_id} ajoutés (fallback)")
                fb_log_action("scrape_page", target=page_id, status="success", details=f"{len(new)} ajoutés")
                return new

            all_targets: List[Dict] = []
            per_post = max(limit // len(post_links), 15)

            for post_url in post_links:
                if len(all_targets) >= limit:
                    break
                commenters = await self._scrape_post_commenters(post_url, per_post)
                all_targets.extend(commenters)
                await random_sleep(2, 4)

            new = [t for t in all_targets if not fb_is_already_targeted(t["profile_url"])]
            if new:
                added = fb_add_targets_bulk(new, source=f"page:{page_id}")
                logger.info(f"[FB] {added} commentateurs de {page_id} ajoutés")
            fb_log_action("scrape_page", target=page_id, status="success", details=f"{len(new)} ajoutés")
            return new

        except Exception as e:
            logger.warning(f"[FB] Erreur scraping page : {e}")
            fb_log_error("scrape_page_error", str(e), "scrape_page")
            return []

    async def _get_post_links(self, limit: int = 8) -> List[str]:
        """Récupère les liens de posts sur la page courante."""
        links, seen = [], set()

        # Scroll pour charger plus de posts
        for _ in range(4):
            await self.page.evaluate("window.scrollBy(0, 700)")
            await random_sleep(1.5, 2.5)

        for sel in POST_LINK_SELECTORS:
            try:
                els = await self.page.query_selector_all(sel)
                for el in els:
                    href = (await el.get_attribute("href") or "").split("?")[0].rstrip("/")
                    if not href or "facebook.com" not in href:
                        continue
                    if any(x in href for x in ["/pages/", "/groups/", "l.facebook.com", "/events/"]):
                        continue
                    if any(x in href for x in ["/posts/", "/permalink/", "/videos/", "/photos/"]):
                        if href not in seen:
                            seen.add(href)
                            links.append(href)
                if len(links) >= limit:
                    break
            except Exception:
                continue

        return links[:limit]

    async def _scrape_post_commenters(self, post_url: str, limit: int) -> List[Dict]:
        """Ouvre un post et scrape les profils des commentateurs."""
        targets = []
        try:
            await self.page.goto(post_url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 4)

            # Scroll pour charger les commentaires
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await random_sleep(1, 2)

            # Essayer de cliquer "Voir plus de commentaires"
            for btn_text in ["Voir plus de commentaires", "View more comments", "Plus de commentaires"]:
                try:
                    btn = self.page.get_by_text(btn_text).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await random_sleep(1.5, 2.5)
                except Exception:
                    pass

            targets = await self._collect_profiles_from_page(limit)
            logger.info(f"[FB] {len(targets)} commentateurs trouvés dans {post_url.split('/')[-1][:30]}")

        except Exception as e:
            logger.warning(f"[FB] Erreur scraping commentaires : {e}")
        return targets

    async def _collect_profiles_from_page(self, limit: int) -> List[Dict]:
        """Collecte les liens de profils visibles sur la page courante."""
        targets, seen = [], set()

        for sel in COMMENT_PROFILE_SELECTORS:
            try:
                els = await self.page.query_selector_all(sel)
                for el in els:
                    href = (await el.get_attribute("href") or "").split("?")[0].rstrip("/")
                    name = (await el.get_attribute("aria-label") or await el.inner_text() or "").strip()[:60]
                    if not href or len(href) < 26:
                        continue
                    if "facebook.com" not in href:
                        continue
                    if any(x in href for x in ["/posts/", "/photos/", "/videos/", "/permalink/",
                                                "l.facebook.com", "/events/", "/groups/", "/pages/"]):
                        continue
                    if href not in seen:
                        seen.add(href)
                        targets.append({"profile_url": href, "name": name})
                if len(targets) >= limit:
                    break
            except Exception:
                continue

        return targets[:limit]

    async def _scroll_and_collect(self, limit: int) -> List[Dict]:
        """Scroll et collecte les profils (pour la liste d'amis)."""
        targets, seen_urls = [], set()
        stall = scroll = 0
        max_scroll = limit // 8 + 25
        await random_sleep(2, 3)
        while len(targets) < limit and scroll < max_scroll:
            prev = len(targets)
            cards = await self.page.query_selector_all(
                'div[role="main"] a[href*="facebook.com/"][aria-label],'
                'div[role="main"] a[href^="https://www.facebook.com/profile"]'
            )
            for card in cards:
                try:
                    href = (await card.get_attribute("href") or "").split("?")[0].rstrip("/")
                    name = await card.get_attribute("aria-label") or ""
                    if not href or "facebook.com" not in href:
                        continue
                    if any(x in href for x in ["/friends", "/photos", "/videos", "/posts", "l.facebook.com"]):
                        continue
                    if href not in seen_urls and len(href) > 25:
                        seen_urls.add(href)
                        targets.append({"profile_url": href, "name": name})
                except Exception:
                    continue
            stall = 0 if len(targets) > prev else stall + 1
            if stall >= 5 or len(targets) >= limit:
                break
            await self.page.evaluate("window.scrollBy(0, 800)")
            await random_sleep(2, 4)
            scroll += 1
        return targets[:limit]

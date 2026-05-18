import random
from typing import List, Dict
from playwright.async_api import Page
from facebook.database import fb_add_targets_bulk, fb_is_already_targeted, fb_log_action, fb_log_error
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)
FB_URL = "https://www.facebook.com"


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
                logger.info(f"[FB] ✓ {added} amis de {friend_id} ajoutés")
            fb_log_action("scrape_friends", target=friend_id, status="success", details=f"{len(new)} ajoutés")
            return new
        except Exception as e:
            logger.warning(f"[FB] Erreur scraping amis : {e}")
            fb_log_error("scrape_error", str(e), "scrape_friends")
            return []

    async def scrape_page_likers(self, page_id: str, limit: int = 200) -> List[Dict]:
        url = page_id if page_id.startswith("http") else f"{FB_URL}/{page_id}"
        logger.info(f"[FB] Scraping likers de la page {page_id}...")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(3, 5)
            if "login" in self.page.url:
                return []
            post_links = await self._get_post_links(5)
            if not post_links:
                fb_log_action("scrape_page", target=page_id, status="error", details="aucun post")
                return []
            all_targets: List[Dict] = []
            per_post = max(limit // len(post_links), 20)
            for post_url in post_links:
                if len(all_targets) >= limit:
                    break
                likers = await self._scrape_post_likers(post_url, per_post)
                all_targets.extend(likers)
                await random_sleep(2, 4)
            new = [t for t in all_targets if not fb_is_already_targeted(t["profile_url"])]
            if new:
                added = fb_add_targets_bulk(new, source=f"page:{page_id}")
                logger.info(f"[FB] ✓ {added} likers de {page_id} ajoutés")
            fb_log_action("scrape_page", target=page_id, status="success", details=f"{len(new)} ajoutés")
            return new
        except Exception as e:
            logger.warning(f"[FB] Erreur scraping page : {e}")
            fb_log_error("scrape_page_error", str(e), "scrape_page")
            return []

    async def _scroll_and_collect(self, limit: int) -> List[Dict]:
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

    async def _get_post_links(self, limit: int = 5) -> List[str]:
        links, seen = [], set()
        for _ in range(3):
            await self.page.evaluate("window.scrollBy(0, 600)")
            await random_sleep(1, 2)
        els = await self.page.query_selector_all('a[href*="/posts/"],a[href*="/permalink/"]')
        for el in els:
            href = (await el.get_attribute("href") or "").split("?")[0].rstrip("/")
            if href and href not in seen and "facebook.com" in href:
                seen.add(href)
                links.append(href)
            if len(links) >= limit:
                break
        return links

    async def _scrape_post_likers(self, post_url: str, limit: int) -> List[Dict]:
        targets = []
        try:
            await self.page.goto(post_url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 4)
            opened = False
            for sel in ['span[aria-label*="personne"] [role="button"]','[aria-label*="reaction"] [role="button"]']:
                try:
                    btn = self.page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await random_sleep(2, 3)
                        opened = True
                        break
                except Exception:
                    continue
            if not opened:
                return []
            targets = await self._scrape_modal(limit)
            await self.page.keyboard.press("Escape")
        except Exception as e:
            logger.warning(f"[FB] Erreur likers post : {e}")
        return targets

    async def _scrape_modal(self, limit: int) -> List[Dict]:
        targets, seen, stall, scroll = [], set(), 0, 0
        await random_sleep(1, 2)
        while len(targets) < limit and scroll < limit // 5 + 15:
            prev = len(targets)
            links = await self.page.query_selector_all('div[role="dialog"] a[href*="facebook.com"]')
            for link in links:
                try:
                    href = (await link.get_attribute("href") or "").split("?")[0].rstrip("/")
                    name = (await link.inner_text() or "").strip()[:60]
                    if not href or "facebook.com" not in href or len(href) < 26:
                        continue
                    if any(x in href for x in ["/posts/", "/photos/", "l.facebook.com"]):
                        continue
                    if href not in seen:
                        seen.add(href)
                        targets.append({"profile_url": href, "name": name})
                except Exception:
                    continue
            stall = 0 if len(targets) > prev else stall + 1
            if stall >= 5 or len(targets) >= limit:
                break
            try:
                modal = await self.page.query_selector('div[role="dialog"]')
                if modal:
                    await modal.evaluate("(el) => el.scrollBy(0, 500)")
                else:
                    await self.page.evaluate("window.scrollBy(0, 500)")
            except Exception:
                pass
            await random_sleep(1.5, 3.0)
            scroll += 1
        return targets[:limit]

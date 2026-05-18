import random
from typing import List, Dict
from playwright.async_api import Page
from facebook.database import fb_add_targets_bulk, fb_is_already_targeted, fb_log_action, fb_log_error
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)

FB_URL    = "https://www.facebook.com"
MBASIC    = "https://mbasic.facebook.com"   # HTML simple, sélecteurs stables


class FbTargetScraper:
    def __init__(self, page: Page):
        self.page = page

    # ── API publique ──────────────────────────────────────────────────────────

    async def scrape_friends_of_friend(self, friend_id: str, limit: int = 200) -> List[Dict]:
        url = f"{MBASIC}/{friend_id.lstrip('/')}/friends"
        logger.info(f"[FB] Scraping amis de {friend_id}...")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 4)
            if "login" in self.page.url:
                return []
            content = await self.page.content()
            if "privée" in content.lower() or "private" in content.lower():
                fb_log_action("scrape_friends", target=friend_id, status="error", details="liste privée")
                return []
            targets = await self._mbasic_collect_profiles(limit)
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
        """Scrape les commentateurs des posts d'une page via mbasic (HTML stable)."""
        logger.info(f"[FB] Scraping commentateurs de {page_id} via mbasic...")
        try:
            post_urls = await self._mbasic_get_post_urls(page_id, max_posts=8)
            logger.info(f"[FB] {len(post_urls)} posts trouvés sur {page_id}")

            if not post_urls:
                fb_log_action("scrape_page", target=page_id, status="error", details="0 posts trouvés")
                return []

            all_targets: List[Dict] = []
            per_post = max(limit // len(post_urls), 15)

            for post_url in post_urls:
                if len(all_targets) >= limit:
                    break
                commenters = await self._mbasic_scrape_post_commenters(post_url, per_post)
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

    # ── mbasic helpers ────────────────────────────────────────────────────────

    async def _mbasic_get_post_urls(self, page_id: str, max_posts: int = 8) -> List[str]:
        """Récupère les URLs des posts récents d'une page via mbasic."""
        url = f"{MBASIC}/{page_id}"
        await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await random_sleep(2, 4)

        if "login" in self.page.url or "checkpoint" in self.page.url:
            logger.warning(f"[FB] Non connecté sur mbasic pour {page_id}")
            return []

        links, seen = [], set()
        # Sur mbasic, les posts ont des liens /story.php ou /permalink/ ou /{page}/posts/
        els = await self.page.query_selector_all('a[href]')
        for el in els:
            href = await el.get_attribute("href") or ""
            href = href.split("?")[0].rstrip("/")
            # Convertir les URLs relatives mbasic en absolues
            if href.startswith("/story.php") or href.startswith("/permalink"):
                href = MBASIC + href
            if not href.startswith("http"):
                continue
            if any(x in href for x in ["story.php", "/permalink/", "/posts/"]):
                full = href.replace("mbasic.facebook.com", "mbasic.facebook.com")
                if full not in seen:
                    seen.add(full)
                    links.append(full)
            if len(links) >= max_posts:
                break

        # Fallback : reconstruire les URLs depuis les attributs data
        if not links:
            els = await self.page.query_selector_all('a[href*="story_fbid"], a[href*="story.php"]')
            for el in els:
                href = await el.get_attribute("href") or ""
                if href and href not in seen:
                    seen.add(href)
                    if not href.startswith("http"):
                        href = MBASIC + href
                    links.append(href)
                if len(links) >= max_posts:
                    break

        return links[:max_posts]

    async def _mbasic_scrape_post_commenters(self, post_url: str, limit: int) -> List[Dict]:
        """Ouvre un post mbasic et collecte les profils des commentateurs."""
        targets = []
        try:
            # S'assurer qu'on utilise mbasic
            mbasic_url = post_url.replace("www.facebook.com", "mbasic.facebook.com")
            await self.page.goto(mbasic_url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 3)

            # Sur mbasic, les commentaires sont directement visibles avec des <a> simples
            # Format : <a href="/username">Nom</a> ou <a href="/profile.php?id=...">
            targets = await self._mbasic_collect_profiles(limit)
            logger.info(f"[FB] {len(targets)} commentateurs dans ce post")

            # Essayer de charger plus de commentaires
            for _ in range(3):
                try:
                    more_btn = self.page.get_by_text("Voir plus de commentaires").first
                    if await more_btn.is_visible(timeout=2000):
                        await more_btn.click()
                        await random_sleep(1.5, 2.5)
                        extra = await self._mbasic_collect_profiles(limit - len(targets))
                        targets.extend(extra)
                except Exception:
                    break

        except Exception as e:
            logger.warning(f"[FB] Erreur scraping post : {e}")
        return targets

    async def _mbasic_collect_profiles(self, limit: int) -> List[Dict]:
        """
        Collecte les liens de profils Facebook sur la page mbasic courante.
        Sur mbasic, les profils ont des URLs simples : /username ou /profile.php?id=XXX
        """
        targets, seen = [], set()
        els = await self.page.query_selector_all('a[href]')

        for el in els:
            try:
                href = await el.get_attribute("href") or ""
                name = (await el.inner_text() or "").strip()[:60]

                # Ignorer les liens vides ou trop courts
                if not href or len(href) < 2:
                    continue

                # Normaliser l'URL
                if href.startswith("/") and not href.startswith("//"):
                    href = "https://www.facebook.com" + href.split("?")[0].rstrip("/")
                elif "facebook.com" in href:
                    href = "https://www.facebook.com" + "/" + href.split("facebook.com/", 1)[-1].split("?")[0].rstrip("/")
                else:
                    continue

                # Filtrer les URLs non-profil
                path = href.replace("https://www.facebook.com", "").strip("/")
                if not path:
                    continue
                skip_patterns = [
                    "posts", "photos", "videos", "permalink", "story",
                    "events", "groups", "pages", "hashtag", "watch",
                    "marketplace", "gaming", "ads", "help", "privacy",
                    "login", "checkpoint", "recover", "settings",
                    "notifications", "messages", "friends", "bookmarks",
                    "search", "explore", "l.facebook", "share",
                ]
                if any(p in path for p in skip_patterns):
                    continue

                # Garder uniquement /username ou /profile.php?id=...
                if "/" in path and not path.startswith("profile.php"):
                    continue  # sous-page d'un profil, pas le profil lui-même

                if href not in seen and name and len(name) > 1:
                    seen.add(href)
                    targets.append({"profile_url": href, "name": name})

                if len(targets) >= limit:
                    break

            except Exception:
                continue

        return targets

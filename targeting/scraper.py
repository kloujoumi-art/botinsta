"""
Scraping des abonnés et interacteurs d'un compte cible.
Navigue dans l'UI Instagram pour collecter des usernames.
"""
import asyncio
import random
from typing import List
from playwright.async_api import Page

from utils.human import random_sleep, scroll_down
from utils.logger import get_logger
from storage.database import add_targets_bulk, is_already_targeted, log_action, log_error

logger = get_logger(__name__)

INSTAGRAM_URL = "https://www.instagram.com"


class TargetScraper:
    def __init__(self, page: Page):
        self.page = page

    async def scrape_followers(self, account: str, limit: int = 50) -> List[str]:
        """
        Scraper les abonnés d'un compte cible en naviguant dans l'UI.
        Retourne la liste des usernames collectés.
        """
        account = account.lstrip("@")
        logger.info(f"Scraping abonnés de @{account} (max {limit})...")

        try:
            # Aller sur le profil
            await self.page.goto(
                f"{INSTAGRAM_URL}/{account}/",
                wait_until="domcontentloaded",
                timeout=25000,
            )
            await random_sleep(3, 6)

            # Vérifier que le profil est public
            if await self._is_private():
                logger.warning(f"@{account} est privé — scraping impossible")
                return []

            # Cliquer sur "Abonnés"
            followers_clicked = await self._click_followers_link(account)
            if not followers_clicked:
                logger.warning(f"Impossible d'ouvrir les abonnés de @{account}")
                return []

            await random_sleep(2, 4)

            # Scraper les usernames dans la modale
            usernames = await self._scrape_modal_usernames(limit)

            # Fermer la modale
            await self.page.keyboard.press("Escape")
            await random_sleep(1, 3)

            # Filtrer et enregistrer
            new_targets = [u for u in usernames if not is_already_targeted(u)]
            if new_targets:
                added = add_targets_bulk(new_targets, source=f"followers:{account}")
                logger.info(f"✓ {added} nouveaux abonnés de @{account} ajoutés comme cibles")
            else:
                logger.info("Aucun nouveau abonné trouvé")

            log_action("scrape_followers", target=account, status="success",
                       details=f"{len(new_targets)} ajoutés")
            return new_targets

        except Exception as e:
            logger.warning(f"Erreur scraping @{account} : {e}")
            log_error("scrape_error", str(e), "scrape_followers")
            log_action("scrape_followers", target=account, status="error", details=str(e))
            return []

    async def _is_private(self) -> bool:
        try:
            content = await self.page.content()
            return "Ce compte est privé" in content or "This Account is Private" in content
        except Exception:
            return False

    async def _click_followers_link(self, account: str) -> bool:
        """Cliquer sur le compteur d'abonnés du profil."""
        selectors = [
            f'a[href="/{account}/followers/"]',
            'a:has-text("abonnés")',
            'a:has-text("followers")',
        ]
        for sel in selectors:
            try:
                elem = self.page.locator(sel).first
                if await elem.is_visible(timeout=4000):
                    await elem.click()
                    return True
            except Exception:
                continue
        return False

    async def _scrape_modal_usernames(self, limit: int) -> List[str]:
        """Défiler dans la modale des abonnés et collecter les usernames."""
        usernames = set()
        scroll_attempts = 0
        max_scroll_attempts = limit // 5 + 10

        # Attendre que la modale se charge
        await random_sleep(2, 4)

        while len(usernames) < limit and scroll_attempts < max_scroll_attempts:
            # Chercher tous les liens de profil dans la modale
            try:
                links = await self.page.query_selector_all(
                    'div[role="dialog"] a[href^="/"], '
                    'div[class*="followers"] a[href^="/"]'
                )
                for link in links:
                    try:
                        href = await link.get_attribute("href")
                        if href and href.startswith("/") and "/" not in href[1:]:
                            username = href.strip("/")
                            if username and len(username) > 0:
                                usernames.add(username)
                    except Exception:
                        pass
            except Exception:
                pass

            if len(usernames) >= limit:
                break

            # Défiler dans la modale
            try:
                modal = await self.page.query_selector('div[role="dialog"]')
                if modal:
                    await self.page.evaluate(
                        'arguments[0].scrollBy(0, 400)',
                        modal
                    )
                else:
                    await self.page.evaluate("window.scrollBy(0, 400)")
            except Exception:
                await self.page.evaluate("window.scrollBy(0, 400)")

            await random_sleep(1.5, 3.5)
            scroll_attempts += 1

        collected = list(usernames)[:limit]
        logger.debug(f"Collecté {len(collected)} usernames")
        return collected

    async def scrape_post_likers(self, post_url: str, limit: int = 30) -> List[str]:
        """Scraper les personnes qui ont liké un post (si accessible)."""
        logger.info(f"Scraping likers de {post_url}...")
        try:
            await self.page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            await random_sleep(3, 5)

            # Cliquer sur le compteur de likes
            like_selectors = [
                'a:has-text("J\'aime")',
                'button:has-text("J\'aime")',
                'span:has-text("J\'aime") a',
            ]

            for sel in like_selectors:
                try:
                    elem = self.page.locator(sel).first
                    if await elem.is_visible(timeout=3000):
                        await elem.click()
                        await random_sleep(2, 4)
                        usernames = await self._scrape_modal_usernames(limit)
                        await self.page.keyboard.press("Escape")

                        if usernames:
                            new = [u for u in usernames if not is_already_targeted(u)]
                            if new:
                                add_targets_bulk(new, source=f"likers:{post_url}")
                                logger.info(f"✓ {len(new)} likers ajoutés comme cibles")
                        return usernames
                except Exception:
                    continue

            return []
        except Exception as e:
            logger.warning(f"Erreur scraping likers : {e}")
            return []

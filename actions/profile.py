"""
Visite de profil Instagram : navigation, lecture bio, défilement des posts.
"""
import asyncio
import random
from playwright.async_api import Page

from safety.limits import DailyLimits
from safety.detector import check_for_anomaly
from utils.human import random_sleep, scroll_feed, idle_gesture
from utils.logger import get_logger
from storage.database import log_action, log_error, update_target_status

logger = get_logger(__name__)

INSTAGRAM_URL = "https://www.instagram.com"


class ProfileAction:
    def __init__(self, page: Page, limits: DailyLimits):
        self.page = page
        self.limits = limits

    async def visit(self, username: str) -> bool:
        if not self.limits.can_visit_profile():
            logger.info("Limite de visites journalières atteinte")
            return False

        username = username.lstrip("@")
        url = f"{INSTAGRAM_URL}/{username}/"

        try:
            logger.info(f"Visite du profil @{username}")
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 5)

            anomaly = await check_for_anomaly(self.page)
            if anomaly != "ok":
                logger.warning(f"Anomalie ({anomaly}) lors de la visite de @{username}")
                return False

            # Vérifier que le profil existe
            if await self._profile_not_found():
                logger.debug(f"Profil @{username} introuvable")
                update_target_status(username, "not_found")
                return False

            # Lire la bio (comportement humain)
            await random_sleep(2, 5)

            # Défiler les posts
            scroll_times = random.randint(2, 5)
            await scroll_feed(self.page, times=scroll_times)

            # Parfois regarder un post
            if random.random() < 0.25:
                await self._peek_at_post()

            self.limits.record_profile_visit()
            update_target_status(username, "visited")
            log_action("visit_profile", target=username, status="success")
            logger.info(f"Profil @{username} visité ✓")
            return True

        except Exception as e:
            logger.warning(f"Erreur visite @{username} : {e}")
            log_error("profile_visit_error", str(e), "visit_profile")
            log_action("visit_profile", target=username, status="error", details=str(e))
            return False

    async def _profile_not_found(self) -> bool:
        try:
            content = await self.page.content()
            return "Page introuvable" in content or "Sorry, this page" in content or "Page Not Found" in content
        except Exception:
            return False

    async def _peek_at_post(self) -> None:
        """Ouvrir brièvement un post puis le fermer."""
        try:
            # Chercher un lien de post
            post_links = await self.page.query_selector_all('a[href*="/p/"]')
            if post_links:
                link = random.choice(post_links[:9])
                await link.click()
                await random_sleep(3, 7)

                # Fermer le post (touche Escape)
                await self.page.keyboard.press("Escape")
                await random_sleep(1, 2)
        except Exception:
            pass

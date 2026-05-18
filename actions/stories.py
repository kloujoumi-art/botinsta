"""
Visionnage de stories Instagram.
"""
import asyncio
import random
from playwright.async_api import Page

from safety.limits import DailyLimits
from safety.detector import check_for_anomaly
from utils.human import random_sleep
from utils.logger import get_logger
from storage.database import log_action, log_error

logger = get_logger(__name__)

STORY_SELECTORS = [
    'canvas[class*="story"]',
    '[aria-label*="story"]',
    '[aria-label*="Story"]',
    '[aria-label*="histoire"]',
    'button[class*="story"]',
]


class StoriesAction:
    def __init__(self, page: Page, limits: DailyLimits):
        self.page = page
        self.limits = limits

    async def view_feed_stories(self) -> bool:
        """Cliquer sur une story depuis la barre en haut du feed."""
        if not self.limits.can_view_story():
            logger.info("Limite de stories journalières atteinte")
            return False

        try:
            # Remonter en haut de page pour voir les stories
            await self.page.evaluate("window.scrollTo(0, 0)")
            await random_sleep(1, 2)

            # Chercher les avatars de stories (cercles colorés)
            story_elements = await self.page.query_selector_all(
                'div[role="button"] canvas, '
                'button[class*="story"], '
                '[data-testid*="story"]'
            )

            if not story_elements:
                # Essayer une autre approche
                story_elements = await self.page.query_selector_all(
                    'div[class*="story"] button, '
                    'section button:first-child'
                )

            if not story_elements:
                logger.debug("Aucune story trouvée")
                return False

            # Cliquer sur une story aléatoire (pas la première, trop prévisible)
            idx = random.randint(0, min(len(story_elements) - 1, 6))
            await story_elements[idx].click()
            await random_sleep(2, 4)

            anomaly = await check_for_anomaly(self.page)
            if anomaly != "ok":
                await self.page.keyboard.press("Escape")
                return False

            # Regarder entre 1 et 4 stories
            num_stories = random.randint(1, 4)
            for i in range(num_stories):
                if not self.limits.can_view_story():
                    break

                # Regarder la story quelques secondes (simuler la lecture)
                watch_time = random.uniform(2.5, 8.0)
                await asyncio.sleep(watch_time)

                self.limits.record_story_view()
                log_action("view_story", status="success", details=f"story {i+1}")
                logger.debug(f"Story {i+1} regardée ({watch_time:.1f}s) ✓")

                # Passer à la story suivante (flèche droite)
                if i < num_stories - 1:
                    await self.page.keyboard.press("ArrowRight")
                    await random_sleep(0.5, 1.5)

            # Fermer les stories
            await self.page.keyboard.press("Escape")
            await random_sleep(1, 3)

            logger.info(f"{num_stories} stories regardées ✓")
            return True

        except Exception as e:
            logger.warning(f"Erreur stories : {e}")
            log_error("stories_error", str(e), "view_story")
            try:
                await self.page.keyboard.press("Escape")
            except Exception:
                pass
            return False

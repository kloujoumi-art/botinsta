"""
Action de like : liker un post depuis le feed ou un profil.
"""
import asyncio
import random
from playwright.async_api import Page

from safety.limits import DailyLimits
from safety.detector import check_for_anomaly
from utils.human import random_sleep, move_mouse_naturally
from utils.logger import get_logger
from storage.database import log_action, log_error

logger = get_logger(__name__)

LIKE_BUTTON_SELECTORS = [
    'svg[aria-label="J\'aime"]',
    'svg[aria-label="Like"]',
    '[aria-label="J\'aime"]',
    '[aria-label="Like"]',
]


class LikeAction:
    def __init__(self, page: Page, limits: DailyLimits):
        self.page = page
        self.limits = limits

    async def like_from_feed(self) -> bool:
        """Liker un post visible dans le feed actuel."""
        if not self.limits.can_like():
            logger.info("Limite de likes journaliers atteinte")
            return False

        try:
            # Chercher tous les boutons like visibles
            liked = False
            for selector in LIKE_BUTTON_SELECTORS:
                buttons = await self.page.query_selector_all(selector)
                if buttons:
                    # Prendre un bouton visible au hasard (pas forcément le premier)
                    visible_buttons = []
                    for btn in buttons[:10]:
                        try:
                            if await btn.is_visible():
                                visible_buttons.append(btn)
                        except Exception:
                            pass

                    if visible_buttons:
                        target_btn = random.choice(visible_buttons)
                        bbox = await target_btn.bounding_box()
                        if bbox:
                            x = bbox["x"] + bbox["width"] / 2
                            y = bbox["y"] + bbox["height"] / 2
                            await move_mouse_naturally(self.page, x, y)
                            await asyncio.sleep(random.uniform(0.3, 0.8))
                            await self.page.mouse.click(x, y)

                            await random_sleep(1, 3)
                            anomaly = await check_for_anomaly(self.page)
                            if anomaly == "block":
                                logger.warning("Blocage détecté après like")
                                return False

                            self.limits.record_like()
                            log_action("like", status="success", details="feed")
                            logger.info("Post liké depuis le feed ✓")
                            liked = True
                            break

            if not liked:
                logger.debug("Aucun bouton like trouvé dans le feed")
            return liked

        except Exception as e:
            logger.warning(f"Erreur like : {e}")
            log_error("like_error", str(e), "like")
            log_action("like", status="error", details=str(e))
            return False

    async def like_post_on_profile(self, username: str) -> bool:
        """Ouvrir un post aléatoire d'un profil et le liker."""
        if not self.limits.can_like():
            return False

        try:
            post_links = await self.page.query_selector_all('a[href*="/p/"]')
            if not post_links:
                return False

            link = random.choice(post_links[:9])
            await link.click()
            await random_sleep(2, 5)

            liked = await self.like_from_feed()

            await random_sleep(1, 3)
            await self.page.keyboard.press("Escape")
            await random_sleep(1, 2)

            return liked
        except Exception as e:
            logger.warning(f"Erreur like sur profil @{username} : {e}")
            return False

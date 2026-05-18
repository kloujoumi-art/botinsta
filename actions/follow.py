"""
Action de follow : visiter un profil et cliquer sur Suivre.
Vérifications de limite et d'anomalie intégrées.
"""
import asyncio
import random
from playwright.async_api import Page

from safety.limits import DailyLimits
from safety.detector import check_for_anomaly
from utils.human import random_sleep, move_mouse_naturally
from utils.logger import get_logger
from storage.database import log_action, log_error, update_target_status

logger = get_logger(__name__)

INSTAGRAM_URL = "https://www.instagram.com"

FOLLOW_BUTTON_SELECTORS = [
    'button:has-text("Suivre")',
    'button:has-text("Follow")',
    'button[class*="follow"]:not([class*="following"])',
]

ALREADY_FOLLOWING_TEXTS = ["Vous suivez", "Following", "Abonné(e)"]
PRIVATE_TEXTS = ["Ce compte est privé", "This Account is Private", "This account is private"]


class FollowAction:
    def __init__(self, page: Page, limits: DailyLimits):
        self.page = page
        self.limits = limits

    async def follow(self, username: str) -> bool:
        if not self.limits.can_follow():
            logger.info("Limite de follows journaliers atteinte")
            return False

        username = username.lstrip("@")

        try:
            # Naviguer vers le profil
            await self.page.goto(
                f"{INSTAGRAM_URL}/{username}/",
                wait_until="domcontentloaded",
                timeout=25000,
            )
            await random_sleep(2, 5)

            anomaly = await check_for_anomaly(self.page)
            if anomaly != "ok":
                logger.warning(f"Anomalie détectée, follow annulé pour @{username}")
                return False

            # Ignorer les comptes privés
            if await self._is_private():
                logger.debug(f"Compte privé ignoré : @{username}")
                update_target_status(username, "skipped")
                return False

            # Vérifier si déjà suivi
            if await self._is_already_following():
                logger.debug(f"Déjà suivi : @{username}")
                update_target_status(username, "already_followed")
                return False

            # Trouver et cliquer le bouton Suivre
            followed = await self._click_follow_button()

            if followed:
                self.limits.record_follow()
                update_target_status(username, "followed")
                log_action("follow", target=username, status="success")
                logger.info(f"Suivi @{username} ✓")
                await random_sleep(3, 7)
                return True
            else:
                logger.debug(f"Bouton Suivre introuvable pour @{username}")
                update_target_status(username, "skipped")
                return False

        except Exception as e:
            logger.warning(f"Erreur follow @{username} : {e}")
            log_error("follow_error", str(e), "follow")
            log_action("follow", target=username, status="error", details=str(e))
            return False

    async def _is_private(self) -> bool:
        try:
            content = await self.page.content()
            return any(t in content for t in PRIVATE_TEXTS)
        except Exception:
            return False

    async def _is_already_following(self) -> bool:
        try:
            content = await self.page.content()
            return any(t.lower() in content.lower() for t in ALREADY_FOLLOWING_TEXTS)
        except Exception:
            return False

    async def _click_follow_button(self) -> bool:
        for selector in FOLLOW_BUTTON_SELECTORS:
            try:
                btn = self.page.locator(selector).first
                if await btn.is_visible(timeout=4000):
                    bbox = await btn.bounding_box()
                    if bbox:
                        x = bbox["x"] + bbox["width"] * random.uniform(0.3, 0.7)
                        y = bbox["y"] + bbox["height"] * random.uniform(0.3, 0.7)
                        await move_mouse_naturally(self.page, x, y)
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                        await self.page.mouse.click(x, y)
                        await random_sleep(1, 3)

                        # Vérifier confirmation
                        anomaly = await check_for_anomaly(self.page)
                        if anomaly == "block":
                            logger.warning("Blocage après follow — arrêt du follow")
                            return False
                        return True
            except Exception:
                continue
        return False

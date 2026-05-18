"""
Visionnage de Reels Instagram.
"""
import asyncio
import random
from playwright.async_api import Page

from safety.limits import DailyLimits
from safety.detector import check_for_anomaly
from utils.human import random_sleep, scroll_down
from utils.logger import get_logger
from storage.database import log_action, log_error

logger = get_logger(__name__)

REELS_URL = "https://www.instagram.com/reels/"


class ReelsAction:
    def __init__(self, page: Page, limits: DailyLimits):
        self.page = page
        self.limits = limits

    async def watch_from_feed(self) -> bool:
        """Aller sur la page Reels et regarder quelques vidéos."""
        if not self.limits.can_view_reel():
            logger.info("Limite de reels journaliers atteinte")
            return False

        try:
            current_url = self.page.url
            if "reels" not in current_url:
                await self.page.goto(REELS_URL, wait_until="domcontentloaded", timeout=20000)
                await random_sleep(3, 6)

            anomaly = await check_for_anomaly(self.page)
            if anomaly != "ok":
                return False

            # Regarder entre 1 et 3 reels
            num_reels = random.randint(1, 3)
            watched = 0

            for i in range(num_reels):
                if not self.limits.can_view_reel():
                    break

                # Regarder le reel (durée réaliste)
                watch_time = random.uniform(8, 35)
                logger.debug(f"Reel {i+1} : regarder {watch_time:.1f}s...")
                await asyncio.sleep(watch_time)

                self.limits.record_reel_view()
                log_action("view_reel", status="success", details=f"reel {i+1}")
                watched += 1

                # Passer au reel suivant en scrollant
                if i < num_reels - 1:
                    await random_sleep(0.5, 1.5)
                    await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await random_sleep(2, 4)

                    anomaly = await check_for_anomaly(self.page)
                    if anomaly != "ok":
                        break

            if watched > 0:
                logger.info(f"{watched} reel(s) regardé(s) ✓")

            return watched > 0

        except Exception as e:
            logger.warning(f"Erreur reels : {e}")
            log_error("reels_error", str(e), "view_reel")
            return False

    async def watch_reel_from_post(self) -> bool:
        """Regarder un reel visible dans le feed."""
        if not self.limits.can_view_reel():
            return False

        try:
            # Chercher des liens vers des reels dans le feed
            reel_links = await self.page.query_selector_all('a[href*="/reel/"]')
            if not reel_links:
                return False

            link = random.choice(reel_links[:5])
            await link.click()
            await random_sleep(2, 4)

            watch_time = random.uniform(8, 25)
            await asyncio.sleep(watch_time)

            self.limits.record_reel_view()
            log_action("view_reel", status="success", details="from_feed")
            logger.info(f"Reel regardé depuis feed ({watch_time:.1f}s) ✓")

            # Revenir en arrière
            await self.page.go_back()
            await random_sleep(2, 4)
            return True

        except Exception as e:
            logger.warning(f"Erreur watch reel from feed : {e}")
            return False

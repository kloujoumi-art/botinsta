import random
from playwright.async_api import Page
from facebook.limits import FbDailyLimits
from facebook.detector import fb_check_anomaly
from facebook.database import fb_log_action, fb_log_error
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)

STORY_SELECTORS = [
    '[aria-label*="torie"] [role="button"]',
    '[aria-label*="Story"] [role="button"]',
    'div[data-pagelet="StoriesRing"] [role="button"]',
]


class FbStoriesAction:
    def __init__(self, page: Page, limits: FbDailyLimits):
        self.page = page
        self.limits = limits

    async def view_feed_stories(self) -> int:
        if not self.limits.can_view_story():
            return 0
        viewed = 0
        try:
            if "facebook.com" not in self.page.url:
                await self.page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=25000)
                await random_sleep(2, 4)

            story_btn = None
            for sel in STORY_SELECTORS:
                try:
                    btns = await self.page.query_selector_all(sel)
                    if btns:
                        story_btn = random.choice(btns[:6])
                        break
                except Exception:
                    continue

            if not story_btn:
                return 0

            await story_btn.click()
            await random_sleep(2, 4)

            max_s = min(5, self.limits.get_remaining()["stories"])
            for _ in range(max_s):
                if await fb_check_anomaly(self.page) != "ok":
                    break
                await random_sleep(2, 5)
                self.limits.record_story_view()
                fb_log_action("view_story", status="success")
                viewed += 1
                try:
                    nxt = await self.page.query_selector('[aria-label="Suivant"][role="button"],[aria-label="Next"][role="button"]')
                    if nxt:
                        await nxt.click()
                        await random_sleep(1, 3)
                    else:
                        break
                except Exception:
                    break

            try:
                cl = await self.page.query_selector('[aria-label="Fermer"][role="button"],[aria-label="Close"][role="button"]')
                if cl:
                    await cl.click()
                else:
                    await self.page.keyboard.press("Escape")
            except Exception:
                await self.page.keyboard.press("Escape")

            logger.info(f"[FB] {viewed} story(s) vues ✓")
            return viewed
        except Exception as e:
            logger.warning(f"[FB] Erreur stories : {e}")
            fb_log_error("story_error", str(e), "view_story")
            return viewed

import random
from playwright.async_api import Page
from facebook.limits import FbDailyLimits
from facebook.detector import fb_check_anomaly
from facebook.database import fb_log_action, fb_log_error
from utils.human import random_sleep, move_mouse_naturally
from utils.logger import get_logger

logger = get_logger(__name__)

LIKE_SELECTORS = [
    '[aria-label="J\'aime"][role="button"]',
    '[aria-label="Like"][role="button"]',
    'div[aria-label="J\'aime"]',
    'div[aria-label="Like"]',
]


class FbLikeAction:
    def __init__(self, page: Page, limits: FbDailyLimits):
        self.page = page
        self.limits = limits

    async def like_from_feed(self) -> bool:
        if not self.limits.can_like():
            return False
        try:
            if "facebook.com" not in self.page.url:
                await self.page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=25000)
                await random_sleep(2, 4)
            for _ in range(random.randint(1, 3)):
                await self.page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                await random_sleep(1, 2)
            for sel in LIKE_SELECTORS:
                try:
                    buttons = await self.page.query_selector_all(sel)
                    unliked = [b for b in buttons if await b.get_attribute("aria-pressed") != "true"]
                    if not unliked:
                        continue
                    btn = random.choice(unliked[:5])
                    bbox = await btn.bounding_box()
                    if not bbox:
                        continue
                    x = bbox["x"] + bbox["width"] * random.uniform(0.3, 0.7)
                    y = bbox["y"] + bbox["height"] * random.uniform(0.3, 0.7)
                    await move_mouse_naturally(self.page, x, y)
                    await random_sleep(0.3, 0.8)
                    await self.page.mouse.click(x, y)
                    await random_sleep(1, 3)
                    if await fb_check_anomaly(self.page) in ("block", "captcha"):
                        return False
                    self.limits.record_like()
                    fb_log_action("like", status="success")
                    logger.info("[FB] Post liké ✓")
                    return True
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"[FB] Erreur like : {e}")
            fb_log_error("like_error", str(e), "like")
        return False

    async def like_page_posts(self, page_identifier: str, count: int = 2) -> int:
        if not self.limits.can_like():
            return 0
        url = page_identifier if page_identifier.startswith("http") else f"https://www.facebook.com/{page_identifier}"
        liked = 0
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 4)
            if await fb_check_anomaly(self.page) != "ok":
                return 0
            for _ in range(random.randint(2, 4)):
                await self.page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                await random_sleep(1, 2)
            for sel in LIKE_SELECTORS:
                if liked >= count:
                    break
                try:
                    buttons = await self.page.query_selector_all(sel)
                    unliked = [b for b in buttons if await b.get_attribute("aria-pressed") != "true"]
                    for btn in unliked[:count - liked]:
                        if not self.limits.can_like():
                            break
                        bbox = await btn.bounding_box()
                        if not bbox:
                            continue
                        x = bbox["x"] + bbox["width"] * random.uniform(0.3, 0.7)
                        y = bbox["y"] + bbox["height"] * random.uniform(0.3, 0.7)
                        await move_mouse_naturally(self.page, x, y)
                        await random_sleep(0.4, 1.0)
                        await self.page.mouse.click(x, y)
                        await random_sleep(2, 4)
                        if await fb_check_anomaly(self.page) in ("block", "captcha"):
                            return liked
                        self.limits.record_like()
                        fb_log_action("like_page", target=page_identifier, status="success")
                        liked += 1
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"[FB] Erreur like page : {e}")
            fb_log_error("like_page_error", str(e), "like_page")
        return liked

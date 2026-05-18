import random
from playwright.async_api import Page
from facebook.limits import FbDailyLimits
from facebook.detector import fb_check_anomaly
from facebook.database import fb_log_action, fb_log_error, fb_update_target_status
from utils.human import random_sleep, move_mouse_naturally
from utils.logger import get_logger

logger = get_logger(__name__)

ADD_SELECTORS = [
    '[aria-label="Ajouter comme ami"][role="button"]',
    '[aria-label="Add friend"][role="button"]',
    'div[aria-label="Ajouter comme ami"]',
    'div[aria-label="Add friend"]',
]
ALREADY_FRIEND = ["Amis", "Friends", "Message", "Demande envoyée", "Request Sent"]
PRIVATE_TEXTS  = ["Ce profil est privé", "This profile is private"]


class FbFriendRequestAction:
    def __init__(self, page: Page, limits: FbDailyLimits):
        self.page = page
        self.limits = limits

    async def send_request(self, profile_url: str, name: str = "") -> bool:
        if not self.limits.can_send_friend_request():
            return False
        try:
            await self.page.goto(profile_url, wait_until="domcontentloaded", timeout=25000)
            await random_sleep(2, 5)

            if await fb_check_anomaly(self.page) != "ok":
                return False

            content = await self.page.content()
            if any(t in content for t in PRIVATE_TEXTS):
                fb_update_target_status(profile_url, "skipped")
                return False
            if any(t in content for t in ALREADY_FRIEND):
                fb_update_target_status(profile_url, "already_friend")
                return False

            for sel in ADD_SELECTORS:
                try:
                    btn = self.page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        bbox = await btn.bounding_box()
                        if not bbox:
                            continue
                        x = bbox["x"] + bbox["width"] * random.uniform(0.3, 0.7)
                        y = bbox["y"] + bbox["height"] * random.uniform(0.3, 0.7)
                        await move_mouse_naturally(self.page, x, y)
                        await random_sleep(0.3, 0.8)
                        await self.page.mouse.click(x, y)
                        await random_sleep(2, 4)

                        if await fb_check_anomaly(self.page) in ("block", "captcha"):
                            return False

                        self.limits.record_friend_request()
                        fb_update_target_status(profile_url, "friend_added")
                        fb_log_action("friend_request", target=name or profile_url, status="success")
                        logger.info(f"[FB] Demande ami → {name or profile_url} ✓")
                        return True
                except Exception:
                    continue

            fb_update_target_status(profile_url, "skipped")
            return False
        except Exception as e:
            logger.warning(f"[FB] Erreur demande ami : {e}")
            fb_log_error("friend_request_error", str(e), "friend_request")
            return False

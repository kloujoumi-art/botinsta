from playwright.async_api import Page
from utils.logger import get_logger
from facebook.database import fb_log_error

logger = get_logger(__name__)

BLOCK_TEXTS    = ["you're temporarily blocked","temporairement bloqué","try again later","réessayez plus tard","action blocked"]
CAPTCHA_TEXTS  = ["security check","vérification de sécurité","confirm your identity","confirmez votre identité"]


async def fb_check_anomaly(page: Page) -> str:
    try:
        content = (await page.content()).lower()
        url = page.url.lower()
        for t in CAPTCHA_TEXTS:
            if t in content:
                fb_log_error("captcha", t, "anomaly")
                return "captcha"
        if "checkpoint" in url or "disabled" in url:
            fb_log_error("checkpoint", url, "anomaly")
            return "checkpoint"
        for t in BLOCK_TEXTS:
            if t in content:
                fb_log_error("block", t, "anomaly")
                return "block"
        if "login" in url and "facebook.com" in url:
            return "login"
        return "ok"
    except Exception:
        return "ok"

import os
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)
FB_URL = "https://www.facebook.com"
DATA_DIR = os.getenv("DATA_DIR", "./data")


class FbLoginManager:
    def __init__(self, browser):
        self.browser = browser

    async def login(self) -> bool:
        c_user = os.getenv("FACEBOOK_C_USER", "").strip()
        xs     = os.getenv("FACEBOOK_XS", "").strip()
        email    = os.getenv("FACEBOOK_EMAIL", "").strip()
        password = os.getenv("FACEBOOK_PASSWORD", "").strip()

        if c_user and xs:
            if await self._cookie_login(c_user, xs):
                return True
            logger.warning("Cookies invalides — tentative via formulaire...")

        if email and password:
            return await self._form_login(email, password)

        logger.error("Aucune méthode de connexion Facebook configurée")
        return False

    async def _cookie_login(self, c_user: str, xs: str) -> bool:
        logger.info("Connexion Facebook via cookies...")
        try:
            cookies = [
                {"name": "c_user", "value": c_user, "domain": ".facebook.com", "path": "/", "secure": True},
                {"name": "xs",     "value": xs,     "domain": ".facebook.com", "path": "/", "secure": True},
            ]
            # Cookies optionnels supplémentaires pour contourner la détection IP cloud
            for name, env in [("datr", "FACEBOOK_DATR"), ("sb", "FACEBOOK_SB"), ("fr", "FACEBOOK_FR")]:
                val = os.getenv(env, "").strip()
                if val:
                    cookies.append({"name": name, "value": val, "domain": ".facebook.com", "path": "/", "secure": True})

            await self.browser.context.add_cookies(cookies)
            await self.browser.page.goto(FB_URL, wait_until="domcontentloaded", timeout=30000)
            await random_sleep(3, 5)
            if await self._is_logged_in():
                logger.info("Connexion Facebook via cookies réussie ✓")
                return True
            url = self.browser.page.url
            logger.warning(f"Cookies Facebook invalides — URL actuelle: {url}")
            await self._save_screenshot("fb_login")
            return False
        except Exception as e:
            logger.error(f"Erreur cookie login Facebook : {e}")
            return False

    async def _form_login(self, email: str, password: str) -> bool:
        logger.info("Connexion Facebook via formulaire...")
        try:
            page = self.browser.page
            await page.goto(FB_URL, wait_until="domcontentloaded", timeout=30000)
            await random_sleep(2, 4)
            await page.fill('input[name="email"]', email)
            await random_sleep(0.5, 1.5)
            await page.fill('input[name="pass"]', password)
            await random_sleep(0.5, 1.0)
            await page.click('button[name="login"]')
            await random_sleep(5, 8)
            if await self._is_logged_in():
                logger.info("Connexion Facebook formulaire réussie ✓")
                return True
            url = self.browser.page.url
            logger.error(f"Connexion Facebook échouée — URL: {url}")
            await self._save_screenshot("fb_login")
            return False
        except Exception as e:
            logger.error(f"Erreur form login Facebook : {e}")
            return False

    async def _save_screenshot(self, name: str) -> None:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            path = os.path.join(DATA_DIR, f"debug_{name}.png")
            await self.browser.page.screenshot(path=path)
            logger.info(f"Screenshot sauvegardé : {path}")
        except Exception as e:
            logger.warning(f"Screenshot échoué : {e}")

    async def _is_logged_in(self) -> bool:
        try:
            url = self.browser.page.url
            content = await self.browser.page.content()
            bad_urls = ("login", "checkpoint", "recover", "two_step", "two-step", "security")
            if "facebook.com" not in url:
                return False
            if any(b in url for b in bad_urls):
                return False
            logged_in_signals = (
                'role="feed"',
                '"__typename":"User"',
                "joyride",
                'aria-label="Facebook"',
                '"USER_ID"',
                "profile_photo_uri",
                '"viewer":{',
            )
            return any(s in content for s in logged_in_signals)
        except Exception:
            return False

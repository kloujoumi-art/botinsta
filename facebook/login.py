import os
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)
FB_URL = "https://www.facebook.com"


class FbLoginManager:
    def __init__(self, browser):
        self.browser = browser

    async def login(self) -> bool:
        c_user = os.getenv("FACEBOOK_C_USER", "").strip()
        xs     = os.getenv("FACEBOOK_XS", "").strip()
        if c_user and xs:
            return await self._cookie_login(c_user, xs)
        email    = os.getenv("FACEBOOK_EMAIL", "").strip()
        password = os.getenv("FACEBOOK_PASSWORD", "").strip()
        if email and password:
            return await self._form_login(email, password)
        logger.error("Aucune méthode de connexion Facebook configurée")
        return False

    async def _cookie_login(self, c_user: str, xs: str) -> bool:
        logger.info("Connexion Facebook via cookies...")
        try:
            await self.browser.context.add_cookies([
                {"name": "c_user", "value": c_user, "domain": ".facebook.com", "path": "/", "secure": True},
                {"name": "xs",     "value": xs,     "domain": ".facebook.com", "path": "/", "secure": True},
            ])
            await self.browser.page.goto(FB_URL, wait_until="domcontentloaded", timeout=30000)
            await random_sleep(3, 5)
            if await self._is_logged_in():
                logger.info("Connexion Facebook via cookies réussie ✓")
                return True
            logger.warning("Cookies Facebook invalides")
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
            await random_sleep(4, 7)
            if await self._is_logged_in():
                logger.info("Connexion Facebook formulaire réussie ✓")
                return True
            logger.error("Connexion Facebook échouée — vérifiez les identifiants ou le 2FA")
            return False
        except Exception as e:
            logger.error(f"Erreur form login Facebook : {e}")
            return False

    async def _is_logged_in(self) -> bool:
        try:
            url = self.browser.page.url
            content = await self.browser.page.content()
            return (
                "facebook.com" in url
                and "login" not in url
                and "checkpoint" not in url
                and (
                    'role="feed"' in content
                    or '"__typename":"User"' in content
                    or "joyride" in content
                    or 'aria-label="Facebook"' in content
                )
            )
        except Exception:
            return False

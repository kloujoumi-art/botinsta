"""
Gestion de la connexion Instagram avec persistance de session (cookies).
"""
import asyncio
import random
from pathlib import Path
from playwright.async_api import Page

from core.browser import BrowserManager
from core.session import get_session_path
from utils.human import random_sleep, type_like_human, micro_pause
from utils.logger import get_logger
from config.settings import get_settings
from storage.database import log_action, log_error

logger = get_logger(__name__)

INSTAGRAM_URL = "https://www.instagram.com"
LOGIN_URL = f"{INSTAGRAM_URL}/accounts/login/"


class LoginManager:
    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.settings = get_settings()
        self.session_file = str(get_session_path(self.settings.instagram_username))

    async def login(self) -> bool:
        page = self.browser.page

        # Essayer d'abord la session sauvegardée
        if await self._try_restore_session(page):
            return True

        # Connexion classique
        return await self._do_login(page)

    async def _try_restore_session(self, page: Page) -> bool:
        if not Path(self.session_file).exists():
            return False

        logger.info("Tentative de restauration de session...")
        await self.browser.load_cookies(self.session_file)
        await page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=30000)
        await random_sleep(3, 6)

        if await self._is_logged_in(page):
            logger.info("Session restaurée ✓")
            log_action("session_restore", status="success")
            return True

        logger.info("Session expirée, nouvelle connexion nécessaire")
        return False

    async def _do_login(self, page: Page) -> bool:
        logger.info("Connexion à Instagram...")
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await random_sleep(3, 6)

            await self._handle_cookie_banner(page)

            # Username
            username_input = await page.wait_for_selector('input[name="username"]', timeout=15000)
            await username_input.click()
            await micro_pause()
            await type_like_human(username_input, self.settings.instagram_username)

            await random_sleep(0.8, 2.0)

            # Password
            password_input = await page.wait_for_selector('input[name="password"]', timeout=5000)
            await password_input.click()
            await micro_pause()
            await type_like_human(password_input, self.settings.instagram_password)

            await random_sleep(1.0, 2.5)

            # Soumettre
            submit_btn = await page.wait_for_selector('button[type="submit"]', timeout=5000)
            await submit_btn.click()

            await random_sleep(5, 9)
            await self._handle_post_login_prompts(page)

            if await self._is_logged_in(page):
                logger.info("Connexion réussie ✓")
                log_action("login", status="success")
                await self.browser.save_cookies(self.session_file)
                return True

            logger.error("Échec de connexion — vérifiez vos identifiants dans .env")
            log_error("login_failed", "Connexion échouée après soumission du formulaire", "login")
            return False

        except Exception as e:
            logger.error(f"Erreur lors de la connexion : {e}")
            log_error("login_exception", str(e), "login")
            return False

    async def _is_logged_in(self, page: Page) -> bool:
        try:
            await page.wait_for_selector(
                '[aria-label="Page d\'accueil"], [aria-label="Home"], svg[aria-label="Home"], nav',
                timeout=6000,
            )
            return True
        except Exception:
            url = page.url
            return (
                "instagram.com" in url
                and "login" not in url
                and "accounts" not in url
                and "challenge" not in url
            )

    async def _handle_cookie_banner(self, page: Page) -> None:
        cookie_selectors = [
            'button:has-text("Tout accepter")',
            'button:has-text("Accept all")',
            'button:has-text("Allow all cookies")',
            '[data-testid="cookie-policy-manage-dialog-accept-button"]',
        ]
        for sel in cookie_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await asyncio.sleep(random.uniform(0.8, 1.8))
                    await btn.click()
                    await random_sleep(1, 2)
                    return
            except Exception:
                continue

    async def _handle_post_login_prompts(self, page: Page) -> None:
        """Fermer les popups post-connexion ('Enregistrer les infos', 'Notifications')."""
        dismiss_texts = [
            "Plus tard",
            "Not now",
            "Not Now",
            "Pas maintenant",
            "Ignorer",
            "Skip",
        ]
        for _ in range(4):
            await random_sleep(2, 4)
            dismissed = False
            for text in dismiss_texts:
                try:
                    btn = page.locator(f'button:has-text("{text}")').first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        logger.debug(f"Popup fermé : '{text}'")
                        dismissed = True
                        break
                except Exception:
                    continue
            if not dismissed:
                break

    async def save_session(self) -> None:
        await self.browser.save_cookies(self.session_file)

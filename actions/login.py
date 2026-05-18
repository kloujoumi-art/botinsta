"""
Gestion de la connexion Instagram.

Ordre de tentative :
  1. Restauration de session (cookies existants)
  2. API Instagram via instagrapi  ← principal (contourne Chrome Headless Shell)
  3. Navigateur (fallback — peu fiable sur IP cloud)
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
SCREENSHOT_DIR = "/data"


async def _take_debug_screenshot(page, name: str) -> None:
    """Sauvegarde un screenshot dans /data pour inspection via le dashboard."""
    try:
        import os
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        path = f"{SCREENSHOT_DIR}/debug_{name}.png"
        await page.screenshot(path=path, full_page=False)
        logger.info(f"Screenshot sauvegardé → {path}")
    except Exception as e:
        logger.warning(f"Screenshot impossible ({name}) : {e}")


class LoginManager:
    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.settings = get_settings()
        self.session_file = str(get_session_path(self.settings.instagram_username))

    async def login(self) -> bool:
        page = self.browser.page

        # 1. Restauration de session existante
        if await self._try_restore_session(page):
            return True

        # 2. API Instagram (principal — fiable depuis les IPs cloud)
        if await self._api_login(page):
            return True

        # 3. Formulaire navigateur (fallback)
        logger.warning("Tentative de connexion via le formulaire navigateur (fallback)...")
        return await self._browser_login(page)

    # ── Méthode 1 : restauration de session ──────────────────────────────────

    async def _try_restore_session(self, page: Page) -> bool:
        if not Path(self.session_file).exists():
            return False

        logger.info("Tentative de restauration de session...")
        await self.browser.load_cookies(self.session_file)
        await page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=45000)
        await random_sleep(3, 6)

        if await self._is_logged_in(page):
            logger.info("Session restaurée ✓")
            log_action("session_restore", status="success")
            return True

        logger.info("Session expirée, nouvelle connexion nécessaire")
        return False

    # ── Méthode 2 : API Instagram (instagrapi) ────────────────────────────────

    async def _api_login(self, page: Page) -> bool:
        logger.info("Connexion via l'API Instagram (instagrapi)...")
        try:
            from actions.api_login import api_login_cookies

            cookies = await api_login_cookies(
                self.settings.instagram_username,
                self.settings.instagram_password,
                self.session_file,
            )

            if not cookies:
                logger.warning("API login : aucun cookie retourné")
                return False

            # Injecter les cookies dans le contexte Playwright
            await page.context.add_cookies(cookies)

            # Naviguer vers Instagram pour vérifier l'authentification
            await page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=45000)
            await random_sleep(4, 7)
            await _take_debug_screenshot(page, "api_login_result")

            if await self._is_logged_in(page):
                logger.info("Connexion API réussie ✓")
                log_action("login", status="success", details="api_login")
                await self.browser.save_cookies(self.session_file)
                await self._handle_post_login_prompts(page)
                return True

            logger.warning("API login : cookies injectés mais non connecté")
            return False

        except Exception as e:
            logger.warning(f"API login échoué : {e}")
            log_error("api_login_error", str(e), "login")
            return False

    # ── Méthode 3 : formulaire navigateur (fallback) ─────────────────────────

    async def _browser_login(self, page: Page) -> bool:
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("load", timeout=25000)
            except Exception:
                pass

            await random_sleep(7, 11)

            current_url = page.url
            page_title = await page.title()
            logger.info(f"Page chargée — URL: {current_url} | Titre: {page_title}")

            await self._handle_cookie_banner(page)

            n_inputs = await page.evaluate("document.querySelectorAll('input').length")
            logger.info(f"Inputs dans le DOM : {n_inputs}")

            try:
                await page.wait_for_selector('form', timeout=20000)
                await random_sleep(2, 3)
            except Exception:
                logger.warning("Aucun <form> trouvé")

            await _take_debug_screenshot(page, "browser_login_page")

            # Trouver le champ username
            username_input = None
            for sel in [
                'input[name="username"]',
                'input[aria-label="Phone number, username, or email"]',
                'input[autocomplete="username"]',
                'input[type="text"]',
            ]:
                try:
                    el = await page.wait_for_selector(sel, timeout=12000)
                    if el:
                        username_input = el
                        break
                except Exception:
                    continue

            if not username_input:
                await _take_debug_screenshot(page, "browser_login_no_input")
                log_error("browser_login_no_input", f"Username input not found on {current_url}", "login")
                return False

            await username_input.click()
            await micro_pause()
            await type_like_human(username_input, self.settings.instagram_username)
            await random_sleep(0.8, 2.0)

            password_input = None
            for sel in ['input[name="password"]', 'input[type="password"]']:
                try:
                    el = await page.wait_for_selector(sel, timeout=8000)
                    if el:
                        password_input = el
                        break
                except Exception:
                    continue

            if not password_input:
                log_error("browser_login_no_password", "Password input not found", "login")
                return False

            await password_input.click()
            await micro_pause()
            await type_like_human(password_input, self.settings.instagram_password)
            await random_sleep(1.0, 2.5)

            submit_btn = None
            for sel in ['button[type="submit"]', 'button:has-text("Log in")', 'button:has-text("Connexion")']:
                try:
                    el = await page.wait_for_selector(sel, timeout=5000)
                    if el:
                        submit_btn = el
                        break
                except Exception:
                    continue

            if not submit_btn:
                log_error("browser_login_no_submit", "Submit button not found", "login")
                return False

            await submit_btn.click()
            await random_sleep(6, 10)
            await self._handle_post_login_prompts(page)

            if await self._is_logged_in(page):
                logger.info("Connexion navigateur réussie ✓")
                log_action("login", status="success", details="browser_login")
                await self.browser.save_cookies(self.session_file)
                await _take_debug_screenshot(page, "login_success")
                return True

            await _take_debug_screenshot(page, "browser_login_failed")
            log_error("browser_login_failed", "Connexion échouée après soumission", "login")
            return False

        except Exception as e:
            logger.error(f"Erreur lors de la connexion navigateur : {e}")
            log_error("browser_login_exception", str(e), "login")
            return False

    # ── Utilitaires ───────────────────────────────────────────────────────────

    async def _is_logged_in(self, page: Page) -> bool:
        try:
            await page.wait_for_selector(
                '[aria-label="Page d\'accueil"], [aria-label="Home"], svg[aria-label="Home"], nav',
                timeout=8000,
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
        for sel in [
            'button:has-text("Tout accepter")',
            'button:has-text("Accept all")',
            'button:has-text("Allow all cookies")',
            '[data-testid="cookie-policy-manage-dialog-accept-button"]',
        ]:
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
        for _ in range(4):
            await random_sleep(2, 4)
            dismissed = False
            for text in ["Plus tard", "Not now", "Not Now", "Pas maintenant", "Ignorer", "Skip"]:
                try:
                    btn = page.locator(f'button:has-text("{text}")').first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        dismissed = True
                        break
                except Exception:
                    continue
            if not dismissed:
                break

    async def save_session(self) -> None:
        await self.browser.save_cookies(self.session_file)

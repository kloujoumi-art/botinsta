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
        logger.debug(f"Screenshot impossible ({name}) : {e}")


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
        await page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=45000)
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
            # Passage par la page d'accueil pour établir l'état JS/cookies initial
            try:
                await page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=30000)
                await random_sleep(2, 4)
            except Exception:
                pass

            # Navigation vers le login
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("load", timeout=25000)
            except Exception:
                pass

            await random_sleep(7, 11)  # laisser React hydrater le DOM

            current_url = page.url
            page_title = await page.title()
            logger.info(f"Page chargée — URL: {current_url} | Titre: {page_title}")

            await self._handle_cookie_banner(page)

            # Audit JS : compter les inputs réellement dans le DOM
            try:
                n_inputs = await page.evaluate("document.querySelectorAll('input').length")
                logger.info(f"Inputs trouvés dans le DOM (JS) : {n_inputs}")
            except Exception:
                pass

            # Attendre que le formulaire de connexion soit présent dans le DOM
            try:
                await page.wait_for_selector('form', timeout=20000)
                logger.info("Formulaire <form> détecté dans le DOM")
                await random_sleep(2, 3)
            except Exception:
                logger.warning("Aucun <form> trouvé après 20s")

            # Screenshot pour voir ce que le bot voit réellement
            await _take_debug_screenshot(page, "login_page")

            # Chercher le champ username avec plusieurs sélecteurs de secours
            username_input = None
            username_selectors = [
                'input[name="username"]',
                'input[aria-label="Phone number, username, or email"]',
                'input[aria-label="Numéro de téléphone, nom d\'utilisateur ou adresse e-mail"]',
                'input[autocomplete="username"]',
            ]

            for sel in username_selectors:
                try:
                    el = await page.wait_for_selector(sel, timeout=15000)
                    if el:
                        logger.info(f"Champ username trouvé : {sel}")
                        username_input = el
                        break
                except Exception:
                    continue

            # Fallback JS : chercher n'importe quel input non-password visible
            if not username_input:
                try:
                    all_inputs = await page.query_selector_all('input')
                    logger.info(f"Fallback JS : {len(all_inputs)} inputs détectés")
                    for inp in all_inputs:
                        try:
                            inp_type = await inp.get_attribute("type") or "text"
                            is_vis   = await inp.is_visible()
                            logger.debug(f"  input type={inp_type} visible={is_vis}")
                            if is_vis and inp_type not in ("password", "hidden", "submit", "checkbox", "radio", "button"):
                                username_input = inp
                                logger.info(f"Username trouvé via fallback JS (type={inp_type})")
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.error(f"Fallback JS échoué : {e}")

            if not username_input:
                page_html = await page.content()
                logger.error(
                    f"Champ username introuvable. URL={current_url} "
                    f"| HTML début: {page_html[:800]}"
                )
                await _take_debug_screenshot(page, "login_failed_no_input")
                log_error("login_no_input", f"Username input not found on {current_url}", "login")
                return False

            await username_input.click()
            await micro_pause()
            await type_like_human(username_input, self.settings.instagram_username)

            await random_sleep(0.8, 2.0)

            # Password
            password_input = None
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[aria-label="Password"]',
                'input[aria-label="Mot de passe"]',
            ]
            for sel in password_selectors:
                try:
                    el = await page.wait_for_selector(sel, timeout=8000)
                    if el:
                        password_input = el
                        break
                except Exception:
                    continue

            if not password_input:
                logger.error("Champ password introuvable")
                log_error("login_no_password", "Password input not found", "login")
                return False

            await password_input.click()
            await micro_pause()
            await type_like_human(password_input, self.settings.instagram_password)

            await random_sleep(1.0, 2.5)

            # Soumettre
            submit_btn = None
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Connexion")',
                'button:has-text("Se connecter")',
            ]
            for sel in submit_selectors:
                try:
                    el = await page.wait_for_selector(sel, timeout=5000)
                    if el:
                        submit_btn = el
                        break
                except Exception:
                    continue

            if not submit_btn:
                logger.error("Bouton submit introuvable")
                log_error("login_no_submit", "Submit button not found", "login")
                return False

            await submit_btn.click()

            await random_sleep(6, 10)
            await self._handle_post_login_prompts(page)

            if await self._is_logged_in(page):
                logger.info("Connexion réussie ✓")
                log_action("login", status="success")
                await self.browser.save_cookies(self.session_file)
                await _take_debug_screenshot(page, "login_success")
                return True

            await _take_debug_screenshot(page, "login_failed_post_submit")
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

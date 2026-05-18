"""
Détecteur d'anomalies Instagram : captcha, blocage d'action, mur de connexion.
Le bot s'arrête immédiatement si une anomalie est détectée.
"""
from playwright.async_api import Page
from utils.logger import get_logger
from storage.database import log_error

logger = get_logger(__name__)

# Textes qui indiquent un blocage Instagram
BLOCK_INDICATORS = [
    "action blocked",
    "action bloquée",
    "something went wrong",
    "une erreur est survenue",
    "try again later",
    "réessayez plus tard",
    "we limit how often",
    "we've noticed some unusual activity",
    "your account has been temporarily",
    "temporarily blocked",
    "temporairement bloqué",
    "challenge_required",
    "please wait a few minutes",
]

CAPTCHA_INDICATORS = [
    "security check",
    "vérification de sécurité",
    "enter the code",
    "verify your identity",
    "vérifiez votre identité",
    "suspicious activity",
    "activité suspecte",
    "confirm your identity",
    "confirmez votre identité",
]

LOGIN_WALL_INDICATORS = [
    "log in",
    "se connecter",
    "create an account",
    "créer un compte",
    "sign up",
    "s'inscrire",
]


async def check_for_anomaly(page: Page) -> str:
    """
    Retourne :
      - 'ok'      si tout va bien
      - 'block'   si Instagram a bloqué l'action
      - 'captcha' si un captcha est détecté
      - 'login'   si le mur de connexion est apparu
    """
    try:
        content = (await page.content()).lower()
        url = page.url.lower()

        # Vérifier captcha
        for indicator in CAPTCHA_INDICATORS:
            if indicator in content:
                logger.warning(f"CAPTCHA détecté : '{indicator}'")
                log_error("captcha", f"Captcha détecté sur {page.url}", "anomaly_check")
                return "captcha"

        # Vérifier blocage action
        for indicator in BLOCK_INDICATORS:
            if indicator in content or indicator in url:
                logger.warning(f"BLOCAGE détecté : '{indicator}'")
                log_error("block", f"Blocage détecté : {indicator}", "anomaly_check")
                return "block"

        # Vérifier mur de connexion
        if "accounts/login" in url or "challenge" in url:
            for indicator in LOGIN_WALL_INDICATORS:
                if indicator in content:
                    logger.warning("Mur de connexion détecté")
                    log_error("login_wall", "Redirigé vers la page de connexion", "anomaly_check")
                    return "login"

        return "ok"

    except Exception as e:
        logger.error(f"Erreur lors de la vérification d'anomalie : {e}")
        return "ok"


async def is_rate_limited(page: Page) -> bool:
    status = await check_for_anomaly(page)
    return status in ("block", "captcha")

"""
Connexion Instagram.

Ordre de priorité :
  1. Cookie sessionid depuis la variable d'env INSTAGRAM_SESSIONID  ← le plus fiable
  2. API privée Instagram via instagrapi (peut être bloquée sur IPs cloud)
"""
import asyncio
import os
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


def _session_from_env() -> list[dict] | None:
    """Retourne des cookies Playwright depuis INSTAGRAM_SESSIONID si défini."""
    session_id = os.getenv("INSTAGRAM_SESSIONID", "").strip()
    if not session_id:
        return None
    logger.info("Utilisation de INSTAGRAM_SESSIONID depuis les variables d'environnement")
    return [
        {
            "name": "sessionid",
            "value": session_id,
            "domain": ".instagram.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        }
    ]


def _do_api_login(username: str, password: str, session_file: str) -> list[dict]:
    """Fonction synchrone — appelée via asyncio.to_thread."""
    from instagrapi import Client
    from instagrapi.exceptions import (
        TwoFactorRequired, ChallengeRequired, BadPassword, UserNotFound,
    )

    cl = Client()
    cl.delay_range = [1, 3]

    # Charger une session existante pour éviter le 2FA répété
    igrapi_file = session_file + ".igrapi.json"
    if Path(igrapi_file).exists():
        try:
            cl.load_settings(igrapi_file)
            logger.info("Session instagrapi chargée depuis le disque")
        except Exception as e:
            logger.warning(f"Session instagrapi invalide : {e}, recréation...")
            cl = Client()
            cl.delay_range = [1, 3]

    try:
        cl.login(username, password)
    except TwoFactorRequired:
        logger.error("2FA activé sur le compte — désactivez-le temporairement dans les paramètres Instagram")
        raise
    except ChallengeRequired:
        logger.error("Instagram demande une vérification de compte (challenge) — connexion manuelle nécessaire")
        raise
    except BadPassword:
        logger.error("Mot de passe incorrect — vérifiez INSTAGRAM_PASSWORD dans .env")
        raise
    except UserNotFound:
        logger.error("Nom d'utilisateur introuvable — vérifiez INSTAGRAM_USERNAME dans .env")
        raise
    except Exception as e:
        logger.error(f"Erreur API login : {e}")
        raise

    # Sauvegarder la session pour les prochaines fois
    Path(igrapi_file).parent.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(igrapi_file)
    logger.info(f"Session instagrapi sauvegardée → {igrapi_file}")

    # Construire la liste de cookies compatible Playwright
    playwright_cookies = []
    for name, value in cl.private.cookies.items():
        playwright_cookies.append({
            "name": name,
            "value": str(value),
            "domain": ".instagram.com",
            "path": "/",
            "secure": True,
            "httpOnly": name in ("sessionid", "rur", "mid"),
            "sameSite": "Lax",
        })

    logger.info(f"API login réussi — {len(playwright_cookies)} cookies prêts pour Playwright")
    return playwright_cookies


async def api_login_cookies(username: str, password: str, session_file: str) -> list[dict]:
    """Retourne des cookies Playwright pour s'authentifier sur Instagram."""
    # Priorité 1 : sessionid depuis variable d'environnement (contourne blocage IP)
    cookies = _session_from_env()
    if cookies:
        return cookies

    # Priorité 2 : instagrapi (API privée)
    logger.info("INSTAGRAM_SESSIONID non défini — tentative via instagrapi...")
    return await asyncio.to_thread(_do_api_login, username, password, session_file)

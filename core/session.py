"""
Gestion de la persistance de session (cookies).
"""
from pathlib import Path
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


def get_session_path(username: str) -> Path:
    settings = get_settings()
    return settings.sessions_dir / f"{username}_session.json"


def session_exists(username: str) -> bool:
    return get_session_path(username).exists()


def delete_session(username: str) -> None:
    path = get_session_path(username)
    if path.exists():
        path.unlink()
        logger.info(f"Session supprimée pour {username}")

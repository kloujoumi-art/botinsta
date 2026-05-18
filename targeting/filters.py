"""
Filtrage des comptes cibles : éliminer les faux comptes et comptes privés.
"""
import re
from typing import List
from utils.logger import get_logger

logger = get_logger(__name__)

# Patterns de noms d'utilisateurs suspects (faux comptes courants)
SUSPICIOUS_PATTERNS = [
    r"^\d{5,}$",                    # Que des chiffres
    r"^[a-z]{2,5}\d{6,}$",         # 2-5 lettres + 6+ chiffres
    r"follow.*back",                # "followback"
    r"follow4follow",
    r"f4f",
    r"l4l",
    r"like4like",
    r"bot\d*$",
]

# Longueur minimale et maximale d'un username réaliste
MIN_USERNAME_LEN = 3
MAX_USERNAME_LEN = 30


def is_suspicious_username(username: str) -> bool:
    """Retourne True si le username semble appartenir à un faux compte."""
    u = username.lower()

    if len(u) < MIN_USERNAME_LEN or len(u) > MAX_USERNAME_LEN:
        return True

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, u):
            logger.debug(f"Username suspect : @{username} (pattern: {pattern})")
            return True

    return False


def filter_targets(usernames: List[str]) -> List[str]:
    """Filtrer une liste de usernames pour ne garder que les comptes réels."""
    filtered = []
    removed = 0

    for username in usernames:
        if is_suspicious_username(username):
            removed += 1
        else:
            filtered.append(username)

    if removed > 0:
        logger.info(f"Filtrage : {removed} comptes suspects éliminés sur {len(usernames)}")

    return filtered


def deduplicate(usernames: List[str]) -> List[str]:
    """Supprimer les doublons en conservant l'ordre."""
    seen = set()
    result = []
    for u in usernames:
        clean = u.lstrip("@").lower().strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result

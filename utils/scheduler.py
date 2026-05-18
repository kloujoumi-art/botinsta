"""
Planificateur de sessions : définit des plages horaires actives pour le bot.
Simule un utilisateur humain qui utilise Instagram à des heures précises.
"""
import random
from datetime import datetime, time
from typing import List, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)

# Plages horaires actives par défaut (réalistes pour un utilisateur humain)
DEFAULT_ACTIVE_HOURS: List[Tuple[int, int]] = [
    (7, 9),    # Matin
    (12, 14),  # Pause déjeuner
    (18, 22),  # Soirée
]


def is_active_time(active_hours: List[Tuple[int, int]] = None) -> bool:
    """Vérifier si l'heure actuelle est dans une plage active."""
    if active_hours is None:
        active_hours = DEFAULT_ACTIVE_HOURS

    now = datetime.now()
    current_hour = now.hour

    for start, end in active_hours:
        if start <= current_hour < end:
            return True
    return False


def seconds_until_next_active(active_hours: List[Tuple[int, int]] = None) -> int:
    """Calculer le nombre de secondes jusqu'à la prochaine plage active."""
    if active_hours is None:
        active_hours = DEFAULT_ACTIVE_HOURS

    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute

    min_wait = 24 * 60  # Maximum 24h

    for start, _ in active_hours:
        start_minutes = start * 60
        if start_minutes > current_minutes:
            wait = start_minutes - current_minutes
        else:
            wait = (24 * 60 - current_minutes) + start_minutes

        if wait < min_wait:
            min_wait = wait

    return min_wait * 60


def random_session_delay() -> int:
    """Délai aléatoire entre deux sessions (en secondes)."""
    # Entre 30 minutes et 2 heures de repos entre sessions
    return random.randint(1800, 7200)


def get_next_session_info() -> dict:
    if is_active_time():
        return {"status": "active", "wait_seconds": 0}
    wait = seconds_until_next_active()
    return {"status": "waiting", "wait_seconds": wait}

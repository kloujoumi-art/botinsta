"""
Contrôle des limites journalières pour éviter les blocages Instagram.
Les limites varient aléatoirement chaque jour (même graine = mêmes valeurs dans la journée).
"""
import hashlib
import random
from datetime import date

from storage.database import get_today_stats, increment_stat
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


def _day_rng() -> random.Random:
    """RNG déterministe pour la journée en cours — change chaque jour automatiquement."""
    seed = int(hashlib.md5(date.today().isoformat().encode()).hexdigest(), 16) % (2 ** 32)
    return random.Random(seed)


def _daily_limit(max_val: int, floor_ratio: float = 0.55) -> int:
    """Retourne un plafond aléatoire entre floor_ratio*max et max pour aujourd'hui."""
    rng = _day_rng()
    return rng.randint(int(max_val * floor_ratio), max_val)


class DailyLimits:
    def __init__(self):
        self.settings = get_settings()
        self._limits = self._compute_today_limits()
        logger.info(
            f"Limites du jour — "
            f"Follows:{self._limits['follows']} "
            f"Likes:{self._limits['likes']} "
            f"Visites:{self._limits['profile_visits']} "
            f"Stories:{self._limits['stories']} "
            f"Reels:{self._limits['reels']}"
        )

    def _compute_today_limits(self) -> dict:
        cfg = self.settings
        rng = _day_rng()

        # Chaque limite varie entre 55 % et 100 % du maximum configuré
        follows = rng.randint(int(cfg.max_follows_per_day * 0.55), cfg.max_follows_per_day)
        likes   = rng.randint(int(cfg.max_likes_per_day * 0.55),   cfg.max_likes_per_day)
        visits  = rng.randint(int(cfg.max_profile_visits_per_day * 0.55), cfg.max_profile_visits_per_day)
        stories = rng.randint(int(cfg.max_stories_per_day * 0.55), cfg.max_stories_per_day)
        reels   = rng.randint(int(cfg.max_reels_per_day * 0.55),   cfg.max_reels_per_day)

        return {
            "follows":        follows,
            "likes":          likes,
            "profile_visits": visits,
            "stories":        stories,
            "reels":          reels,
        }

    def _stats(self) -> dict:
        return get_today_stats()

    # ── Vérifications ──────────────────────────────────────────────────────

    def can_follow(self) -> bool:
        return self._stats().get("follows", 0) < self._limits["follows"]

    def can_like(self) -> bool:
        return self._stats().get("likes", 0) < self._limits["likes"]

    def can_visit_profile(self) -> bool:
        return self._stats().get("profile_visits", 0) < self._limits["profile_visits"]

    def can_view_story(self) -> bool:
        return self._stats().get("stories_viewed", 0) < self._limits["stories"]

    def can_view_reel(self) -> bool:
        return self._stats().get("reels_viewed", 0) < self._limits["reels"]

    # ── Enregistrements ────────────────────────────────────────────────────

    def record_follow(self) -> None:
        increment_stat("follows")
        logger.debug("✓ Follow enregistré")

    def record_like(self) -> None:
        increment_stat("likes")
        logger.debug("✓ Like enregistré")

    def record_profile_visit(self) -> None:
        increment_stat("profile_visits")
        logger.debug("✓ Visite profil enregistrée")

    def record_story_view(self) -> None:
        increment_stat("stories_viewed")
        logger.debug("✓ Story vue enregistrée")

    def record_reel_view(self) -> None:
        increment_stat("reels_viewed")
        logger.debug("✓ Reel vu enregistré")

    # ── Informations ───────────────────────────────────────────────────────

    def get_remaining(self) -> dict:
        s = self._stats()
        lim = self._limits
        return {
            "follows":        max(0, lim["follows"]        - s.get("follows", 0)),
            "likes":          max(0, lim["likes"]          - s.get("likes", 0)),
            "profile_visits": max(0, lim["profile_visits"] - s.get("profile_visits", 0)),
            "stories":        max(0, lim["stories"]        - s.get("stories_viewed", 0)),
            "reels":          max(0, lim["reels"]          - s.get("reels_viewed", 0)),
        }

    def is_daily_limit_reached(self) -> bool:
        return all(v == 0 for v in self.get_remaining().values())

    def summary(self) -> str:
        s = self._stats()
        lim = self._limits
        return (
            f"Follows {s.get('follows',0)}/{lim['follows']} "
            f"| Likes {s.get('likes',0)}/{lim['likes']} "
            f"| Visites {s.get('profile_visits',0)}/{lim['profile_visits']} "
            f"| Stories {s.get('stories_viewed',0)}/{lim['stories']} "
            f"| Reels {s.get('reels_viewed',0)}/{lim['reels']}"
        )

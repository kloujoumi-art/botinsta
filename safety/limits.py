"""
Contrôle des limites journalières pour éviter les blocages Instagram.
Chaque action est vérifiée AVANT d'être exécutée.
"""
from storage.database import get_today_stats, increment_stat
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


class DailyLimits:
    def __init__(self):
        self.settings = get_settings()

    def _stats(self) -> dict:
        return get_today_stats()

    # ── Vérifications ──────────────────────────────────────────────────────

    def can_follow(self) -> bool:
        return self._stats().get("follows", 0) < self.settings.max_follows_per_day

    def can_like(self) -> bool:
        return self._stats().get("likes", 0) < self.settings.max_likes_per_day

    def can_visit_profile(self) -> bool:
        return self._stats().get("profile_visits", 0) < self.settings.max_profile_visits_per_day

    def can_view_story(self) -> bool:
        return self._stats().get("stories_viewed", 0) < self.settings.max_stories_per_day

    def can_view_reel(self) -> bool:
        return self._stats().get("reels_viewed", 0) < self.settings.max_reels_per_day

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
        cfg = self.settings
        return {
            "follows":       max(0, cfg.max_follows_per_day         - s.get("follows", 0)),
            "likes":         max(0, cfg.max_likes_per_day           - s.get("likes", 0)),
            "profile_visits":max(0, cfg.max_profile_visits_per_day  - s.get("profile_visits", 0)),
            "stories":       max(0, cfg.max_stories_per_day         - s.get("stories_viewed", 0)),
            "reels":         max(0, cfg.max_reels_per_day           - s.get("reels_viewed", 0)),
        }

    def is_daily_limit_reached(self) -> bool:
        remaining = self.get_remaining()
        return all(v == 0 for v in remaining.values())

    def summary(self) -> str:
        s = self._stats()
        r = self.get_remaining()
        return (
            f"Follows {s.get('follows',0)}/{self.settings.max_follows_per_day} "
            f"| Likes {s.get('likes',0)}/{self.settings.max_likes_per_day} "
            f"| Visites {s.get('profile_visits',0)}/{self.settings.max_profile_visits_per_day} "
            f"| Stories {s.get('stories_viewed',0)}/{self.settings.max_stories_per_day} "
            f"| Reels {s.get('reels_viewed',0)}/{self.settings.max_reels_per_day}"
        )

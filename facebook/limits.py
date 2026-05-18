import hashlib
import random
from datetime import date
from facebook.database import fb_get_today_stats, fb_increment_stat
from utils.logger import get_logger

logger = get_logger(__name__)


def _day_rng() -> random.Random:
    seed = int(hashlib.md5(("fb" + date.today().isoformat()).encode()).hexdigest(), 16) % (2 ** 32)
    return random.Random(seed)


class FbDailyLimits:
    def __init__(self, max_friend_requests: int = 15, max_likes: int = 40, max_stories: int = 30):
        rng = _day_rng()
        self._limits = {
            "friend_requests": rng.randint(int(max_friend_requests * 0.55), max_friend_requests),
            "likes":           rng.randint(int(max_likes * 0.55),           max_likes),
            "stories":         rng.randint(int(max_stories * 0.55),         max_stories),
        }
        logger.info(
            f"[FB] Limites du jour — "
            f"Demandes ami:{self._limits['friend_requests']} "
            f"Likes:{self._limits['likes']} "
            f"Stories:{self._limits['stories']}"
        )

    def _stats(self): return fb_get_today_stats()

    def can_send_friend_request(self) -> bool:
        return self._stats().get("friend_requests", 0) < self._limits["friend_requests"]

    def can_like(self) -> bool:
        return self._stats().get("likes", 0) < self._limits["likes"]

    def can_view_story(self) -> bool:
        return self._stats().get("stories_viewed", 0) < self._limits["stories"]

    def record_friend_request(self): fb_increment_stat("friend_requests")
    def record_like(self):           fb_increment_stat("likes")
    def record_story_view(self):     fb_increment_stat("stories_viewed")

    def get_remaining(self) -> dict:
        s = self._stats()
        return {
            "friend_requests": max(0, self._limits["friend_requests"] - s.get("friend_requests", 0)),
            "likes":           max(0, self._limits["likes"]           - s.get("likes", 0)),
            "stories":         max(0, self._limits["stories"]         - s.get("stories_viewed", 0)),
        }

    def is_daily_limit_reached(self) -> bool:
        return all(v == 0 for v in self.get_remaining().values())

    def summary(self) -> str:
        s = self._stats()
        l = self._limits
        return (
            f"[FB] Ami {s.get('friend_requests',0)}/{l['friend_requests']} "
            f"| Likes {s.get('likes',0)}/{l['likes']} "
            f"| Stories {s.get('stories_viewed',0)}/{l['stories']}"
        )

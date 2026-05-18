import asyncio
import hashlib
import os
import random
from datetime import date, datetime
from typing import Optional

from core.browser import BrowserManager
from facebook.login import FbLoginManager
from facebook.feed import FbFeedAction
from facebook.like import FbLikeAction
from facebook.stories import FbStoriesAction
from facebook.friend_request import FbFriendRequestAction
from facebook.scraper import FbTargetScraper
from facebook.limits import FbDailyLimits
from facebook.detector import fb_check_anomaly
from facebook.database import fb_init_db, fb_get_pending_targets, fb_log_action, fb_log_error
from utils.logger import get_logger

logger = get_logger(__name__)


def _day_rng() -> random.Random:
    seed = int(hashlib.md5(("fb" + date.today().isoformat()).encode()).hexdigest(), 16) % (2 ** 32)
    return random.Random(seed)


def _get_fb_settings():
    target_friends_raw = os.getenv("TARGET_FRIENDS", "")
    target_pages_raw   = os.getenv("TARGET_PAGES", "")
    return {
        "target_friends":          [f.strip() for f in target_friends_raw.split(",") if f.strip()],
        "target_pages":            [p.strip() for p in target_pages_raw.split(",") if p.strip()],
        "max_friend_requests":     int(os.getenv("MAX_FRIEND_REQUESTS_PER_DAY", "15")),
        "max_likes":               int(os.getenv("FB_MAX_LIKES_PER_DAY", "40")),
        "max_stories":             int(os.getenv("FB_MAX_STORIES_PER_DAY", "30")),
        "min_delay":               float(os.getenv("FB_MIN_ACTION_DELAY", "5")),
        "max_delay":               float(os.getenv("FB_MAX_ACTION_DELAY", "15")),
        "max_targets_per_scrape":  int(os.getenv("MAX_TARGETS_PER_SCRAPE", "200")),
    }


class FbBotEngine:
    def __init__(self):
        self.cfg = _get_fb_settings()
        self.limits = FbDailyLimits(
            max_friend_requests=self.cfg["max_friend_requests"],
            max_likes=self.cfg["max_likes"],
            max_stories=self.cfg["max_stories"],
        )
        self.browser = BrowserManager()
        self.running = False
        self.paused  = False
        self.login_status = "pending"
        self._consecutive_errors = 0
        self._action_count = 0
        self._scrape_every = random.randint(10, 18)
        self._force_scrape = False
        rng = _day_rng()
        self._delays = {
            "min":            rng.uniform(self.cfg["min_delay"] * 0.8, self.cfg["min_delay"] * 1.4),
            "max":            rng.uniform(self.cfg["max_delay"] * 0.8, self.cfg["max_delay"] * 1.4),
            "long_prob":      rng.uniform(0.05, 0.15),
            "long_min":       rng.uniform(120, 240),
            "long_max":       rng.uniform(400, 700),
        }

    async def initialize(self) -> bool:
        fb_init_db()
        await self.browser.start()
        if not await FbLoginManager(self.browser).login():
            self.login_status = "failed"
            await self.browser.close()
            return False
        self.login_status = "success"
        logger.info("[FB] Bot initialisé ✓")
        if self.cfg["target_friends"] or self.cfg["target_pages"]:
            await self._scrape_new_targets()
        return True

    async def run(self) -> None:
        for attempt in range(1, 11):
            if await self.initialize():
                break
            logger.warning(f"[FB] Connexion échouée ({attempt}/10) — retry dans 5 min...")
            self.browser = BrowserManager()
            await asyncio.sleep(300)
        else:
            logger.error("[FB] Impossible de se connecter après 10 tentatives.")
            return

        self.running = True
        logger.info(f"[FB] Bot démarré — {datetime.now().strftime('%H:%M:%S')}")
        logger.info(self.limits.summary())

        try:
            while self.running:
                if self.paused:
                    await asyncio.sleep(5)
                    continue
                if self.limits.is_daily_limit_reached():
                    logger.info("[FB] Limites atteintes — pause 1h")
                    await asyncio.sleep(3600)
                    continue
                if self._consecutive_errors >= 5:
                    logger.warning("[FB] 5 erreurs consécutives — pause 30 min")
                    await asyncio.sleep(1800)
                    self._consecutive_errors = 0
                    continue

                if self._force_scrape:
                    self._force_scrape = False
                    await self._scrape_new_targets()

                self._action_count += 1
                if self._action_count >= self._scrape_every:
                    self._action_count = 0
                    self._scrape_every = random.randint(10, 18)
                    await self._scrape_new_targets()

                try:
                    await self._execute_action()
                    self._consecutive_errors = 0
                except Exception as e:
                    self._consecutive_errors += 1
                    logger.error(f"[FB] Erreur action : {e}")
                    fb_log_error("action_error", str(e))
                    await asyncio.sleep(random.uniform(30, 90))

                await asyncio.sleep(random.uniform(self._delays["min"], self._delays["max"]))
                if random.random() < self._delays["long_prob"]:
                    pause = random.uniform(self._delays["long_min"], self._delays["long_max"])
                    logger.info(f"[FB] Pause naturelle {pause:.0f}s...")
                    await asyncio.sleep(pause)

        except Exception as e:
            logger.error(f"[FB] Erreur critique : {e}")
            fb_log_error("critical_error", str(e))
        finally:
            self.running = False
            await self.browser.close()

    async def _execute_action(self) -> None:
        page = self.browser.page
        remaining = self.limits.get_remaining()
        anomaly = await fb_check_anomaly(page)
        if anomaly in ("captcha", "checkpoint"):
            logger.error(f"[FB] {anomaly} détecté — arrêt")
            self.running = False
            return
        if anomaly == "block":
            await asyncio.sleep(1800)
            return
        if anomaly == "login":
            await FbLoginManager(self.browser).login()
            return

        rng = _day_rng()
        pool = ["scroll_feed"] * rng.randint(4, 7)
        if remaining["stories"] > 0:
            pool += ["view_stories"] * rng.randint(1, 3)
        if remaining["likes"] > 0:
            pool += ["like_post"] * rng.randint(2, 4)
        if remaining["likes"] > 0 and self.cfg["target_pages"]:
            pool += ["like_page"] * rng.randint(1, 2)
        if remaining["friend_requests"] > 0:
            pool += ["friend_request"] * rng.randint(1, 2)

        if not pool:
            await asyncio.sleep(300)
            return

        action = random.choice(pool)
        logger.info(f"[FB] Action : [{action}] | Restants : {remaining}")

        if action == "scroll_feed":
            await FbFeedAction(page).scroll()
        elif action == "like_post":
            await FbLikeAction(page, self.limits).like_from_feed()
        elif action == "like_page":
            pid = random.choice(self.cfg["target_pages"])
            await FbLikeAction(page, self.limits).like_page_posts(pid, count=random.randint(1, 2))
        elif action == "view_stories":
            await FbStoriesAction(page, self.limits).view_feed_stories()
        elif action == "friend_request":
            targets = fb_get_pending_targets(10)
            if targets:
                t = random.choice(targets)
                await FbFriendRequestAction(page, self.limits).send_request(t["profile_url"], t.get("name", ""))
            else:
                await self._scrape_new_targets()

    async def _scrape_new_targets(self) -> None:
        scraper = FbTargetScraper(self.browser.page)
        sources = (["friends"] * 2 if self.cfg["target_friends"] else []) + \
                  (["pages"]   * 1 if self.cfg["target_pages"]   else [])
        if not sources:
            return
        src = random.choice(sources)
        if src == "friends":
            f = random.choice(self.cfg["target_friends"])
            await scraper.scrape_friends_of_friend(f, self.cfg["max_targets_per_scrape"])
        else:
            p = random.choice(self.cfg["target_pages"])
            await scraper.scrape_page_likers(p, self.cfg["max_targets_per_scrape"])

    def stop(self):   self.running = False
    def pause(self):  self.paused = True
    def resume(self): self.paused = False

    @property
    def status(self) -> str:
        if not self.running: return "stopped"
        if self.paused:      return "paused"
        return "running"

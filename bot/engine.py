"""
Moteur principal du bot : orchestre toutes les actions, gère les pauses,
vérifie les limites et les anomalies à chaque cycle.
"""
import asyncio
import hashlib
import random
from datetime import date, datetime
from typing import Optional

from core.browser import BrowserManager
from actions.login import LoginManager
from actions.feed import FeedAction
from actions.profile import ProfileAction
from actions.follow import FollowAction
from actions.like import LikeAction
from actions.stories import StoriesAction
from actions.reels import ReelsAction
from targeting.scraper import TargetScraper
from targeting.filters import filter_targets, deduplicate
from safety.limits import DailyLimits
from safety.detector import check_for_anomaly
from storage.database import init_db, get_pending_targets, log_action, log_error
from utils.human import random_sleep, think_pause, idle_gesture
from utils.scheduler import is_active_time, seconds_until_next_active
from utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger(__name__)


def _day_rng() -> random.Random:
    seed = int(hashlib.md5(date.today().isoformat().encode()).hexdigest(), 16) % (2 ** 32)
    return random.Random(seed)


class BotEngine:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.limits = DailyLimits()
        self.browser = BrowserManager()
        self.running = False
        self.paused = False
        self.login_status = "pending"   # pending / success / failed
        self._consecutive_errors = 0
        self._MAX_CONSECUTIVE_ERRORS = 5
        self._daily_delays = self._compute_daily_delays()
        self._action_count = 0
        self._scrape_every = random.randint(12, 20)  # scrape forcé toutes les N actions
        self._force_scrape = False                   # déclenché depuis le dashboard

    def _compute_daily_delays(self) -> dict:
        rng = _day_rng()
        # Délais min/max varient chaque jour dans une plage raisonnable
        min_delay = rng.uniform(
            self.settings.min_action_delay * 0.8,
            self.settings.min_action_delay * 1.4,
        )
        max_delay = rng.uniform(
            self.settings.max_action_delay * 0.8,
            self.settings.max_action_delay * 1.4,
        )
        # Probabilité de pause longue : entre 5 % et 15 %
        long_pause_prob = rng.uniform(0.05, 0.15)
        long_pause_min  = rng.uniform(90, 180)
        long_pause_max  = rng.uniform(300, 600)
        return {
            "min_delay":       min_delay,
            "max_delay":       max_delay,
            "long_pause_prob": long_pause_prob,
            "long_pause_min":  long_pause_min,
            "long_pause_max":  long_pause_max,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        init_db()
        await self.browser.start()

        login_manager = LoginManager(self.browser)
        if not await login_manager.login():
            self.login_status = "failed"
            logger.error("Impossible de se connecter à Instagram. Vérifiez vos identifiants dans .env")
            await self.browser.close()
            return False

        self.login_status = "success"
        logger.info("Bot initialisé avec succès ✓")
        return True

    async def run(self) -> None:
        # Retry login jusqu'à 10 fois (toutes les 5 min) avant d'abandonner
        for attempt in range(1, 11):
            if await self.initialize():
                break
            logger.warning(
                f"Connexion échouée (tentative {attempt}/10) — "
                f"nouvelle tentative dans 5 min..."
            )
            # Recréer le navigateur proprement avant le prochain essai
            self.browser = BrowserManager()
            await asyncio.sleep(300)
        else:
            logger.error("Impossible de se connecter après 10 tentatives. Arrêt.")
            return

        self.running = True
        session_start = datetime.now()
        logger.info(f"Bot démarré — {datetime.now().strftime('%H:%M:%S')}")
        logger.info(f"Limites du jour : {self.limits.summary()}")

        # Scrape initial après running=True pour afficher le bon statut dans le dashboard
        if self.settings.target_accounts:
            logger.info("Scrape initial des cibles au démarrage...")
            try:
                await self._scrape_new_targets()
            except Exception as e:
                logger.warning(f"Scrape initial échoué (non bloquant) : {e}")

        try:
            while self.running:
                # Pause si demandé
                if self.paused:
                    await asyncio.sleep(5)
                    continue

                # Vérifier plages horaires actives
                if not is_active_time():
                    wait_s = seconds_until_next_active()
                    logger.info(f"Hors plage horaire — reprise dans {wait_s // 60} min")
                    await asyncio.sleep(min(wait_s, 3600))
                    continue

                # Vérifier limites journalières
                if self.limits.is_daily_limit_reached():
                    logger.info("Toutes les limites journalières atteintes — pause 1h")
                    await asyncio.sleep(3600)
                    continue

                # Vérifier les erreurs consécutives
                if self._consecutive_errors >= self._MAX_CONSECUTIVE_ERRORS:
                    logger.warning(f"{self._consecutive_errors} erreurs consécutives — pause 30 min")
                    await asyncio.sleep(1800)
                    self._consecutive_errors = 0
                    continue

                # Scrape forcé depuis le dashboard
                if self._force_scrape:
                    self._force_scrape = False
                    logger.info("Scrape forcé depuis le dashboard...")
                    await self._scrape_new_targets()

                # Scrape périodique toutes les N actions
                self._action_count += 1
                if self._action_count >= self._scrape_every and self.settings.target_accounts:
                    self._action_count = 0
                    self._scrape_every = random.randint(12, 20)
                    logger.info("Scrape périodique des cibles...")
                    await self._scrape_new_targets()

                # Exécuter une action
                try:
                    await self._execute_random_action()
                    self._consecutive_errors = 0
                except Exception as e:
                    self._consecutive_errors += 1
                    logger.error(f"Erreur action : {e}")
                    log_error("action_error", str(e))
                    await asyncio.sleep(random.uniform(30, 90))

                # Délai entre actions (valeurs du jour)
                delay = random.uniform(
                    self._daily_delays["min_delay"],
                    self._daily_delays["max_delay"],
                )
                await asyncio.sleep(delay)

                # Pause longue aléatoire (probabilité et durée varient chaque jour)
                if random.random() < self._daily_delays["long_pause_prob"]:
                    pause = random.uniform(
                        self._daily_delays["long_pause_min"],
                        self._daily_delays["long_pause_max"],
                    )
                    logger.info(f"Pause naturelle de {pause:.0f}s...")
                    await asyncio.sleep(pause)

        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur")
        except Exception as e:
            logger.error(f"Erreur critique : {e}")
            log_error("critical_error", str(e))
        finally:
            self.running = False
            await self.browser.close()
            logger.info("Bot arrêté")

    # ── Actions ───────────────────────────────────────────────────────────

    async def _execute_random_action(self) -> None:
        page = self.browser.page
        remaining = self.limits.get_remaining()

        # Vérification d'anomalie globale avant chaque action
        anomaly = await check_for_anomaly(page)
        if anomaly == "captcha":
            logger.error("CAPTCHA détecté ! Arrêt du bot pour intervention manuelle.")
            self.running = False
            return
        if anomaly == "block":
            logger.warning("Blocage d'action détecté — pause 30 min")
            await asyncio.sleep(1800)
            return
        if anomaly == "login":
            logger.warning("Mur de connexion — tentative de reconnexion")
            login_manager = LoginManager(self.browser)
            await login_manager.login()
            return

        # Construire le pool d'actions pondérées (poids varient chaque jour)
        rng = _day_rng()
        w_scroll  = rng.randint(4, 7)
        w_visit   = rng.randint(2, 4)
        w_stories = rng.randint(1, 3)
        w_reel    = rng.randint(1, 3)
        w_like    = rng.randint(1, 3)
        w_follow  = rng.randint(1, 2)

        pool = []
        pool += ["scroll_feed"] * w_scroll
        if remaining["profile_visits"] > 0:
            pool += ["visit_profile"] * w_visit
        if remaining["stories"] > 0:
            pool += ["view_stories"] * w_stories
        if remaining["reels"] > 0:
            pool += ["view_reel"] * w_reel
        if remaining["likes"] > 0:
            pool += ["like_post"] * w_like
        if remaining["follows"] > 0:
            pool += ["follow_user"] * w_follow

        if not pool:
            await asyncio.sleep(300)
            return

        action = random.choice(pool)
        logger.info(f"Action choisie : [{action}] | Restants : {remaining}")

        if action == "scroll_feed":
            await FeedAction(page).scroll()

        elif action == "visit_profile":
            targets = get_pending_targets(10)
            if targets:
                target = random.choice(targets)
                await ProfileAction(page, self.limits).visit(target["username"])
            else:
                await self._scrape_new_targets()

        elif action == "like_post":
            like_action = LikeAction(page, self.limits)
            # Essayer depuis le feed d'abord
            if not await like_action.like_from_feed():
                await FeedAction(page).scroll()

        elif action == "view_stories":
            # S'assurer d'être sur le feed pour voir les stories
            if "instagram.com/" not in page.url or "reel" in page.url:
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
                await random_sleep(2, 4)
            await StoriesAction(page, self.limits).view_feed_stories()

        elif action == "view_reel":
            await ReelsAction(page, self.limits).watch_from_feed()

        elif action == "follow_user":
            targets = get_pending_targets(5)
            if targets:
                target = random.choice(targets)
                await FollowAction(page, self.limits).follow(target["username"])
            else:
                await self._scrape_new_targets()

    async def _scrape_new_targets(self) -> None:
        if not self.settings.target_accounts:
            logger.warning("Aucun TARGET_ACCOUNTS configuré dans .env")
            return

        account = random.choice(self.settings.target_accounts)
        scraper = TargetScraper(self.browser.page)
        raw = await scraper.scrape_followers(account, limit=self.settings.max_targets_per_scrape)
        filtered = filter_targets(deduplicate(raw))
        logger.info(f"Scraping terminé : {len(filtered)} cibles après filtrage")

    # ── Contrôle externe ──────────────────────────────────────────────────

    def stop(self) -> None:
        self.running = False

    def pause(self) -> None:
        self.paused = True
        logger.info("Bot mis en pause")

    def resume(self) -> None:
        self.paused = False
        logger.info("Bot repris")

    @property
    def status(self) -> str:
        if not self.running:
            return "stopped"
        if self.paused:
            return "paused"
        return "running"

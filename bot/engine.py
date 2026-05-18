"""
Moteur principal du bot : orchestre toutes les actions, gère les pauses,
vérifie les limites et les anomalies à chaque cycle.
"""
import asyncio
import random
from datetime import datetime
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


class BotEngine:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.limits = DailyLimits()
        self.browser = BrowserManager()
        self.running = False
        self.paused = False
        self._consecutive_errors = 0
        self._MAX_CONSECUTIVE_ERRORS = 5

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        init_db()
        await self.browser.start()

        login_manager = LoginManager(self.browser)
        if not await login_manager.login():
            logger.error("Impossible de se connecter à Instagram. Vérifiez vos identifiants dans .env")
            await self.browser.close()
            return False

        logger.info("Bot initialisé avec succès ✓")
        return True

    async def run(self) -> None:
        if not await self.initialize():
            return

        self.running = True
        session_start = datetime.now()
        logger.info(f"Bot démarré — {datetime.now().strftime('%H:%M:%S')}")
        logger.info(f"Limites du jour : {self.limits.summary()}")

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

                # Exécuter une action
                try:
                    await self._execute_random_action()
                    self._consecutive_errors = 0
                except Exception as e:
                    self._consecutive_errors += 1
                    logger.error(f"Erreur action : {e}")
                    log_error("action_error", str(e))
                    await asyncio.sleep(random.uniform(30, 90))

                # Délai entre actions
                delay = random.uniform(
                    self.settings.min_action_delay,
                    self.settings.max_action_delay,
                )
                await asyncio.sleep(delay)

                # Pause longue aléatoire (simuler distraction)
                if random.random() < 0.08:
                    pause = random.uniform(120, 480)
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

        # Construire le pool d'actions pondérées
        pool = []
        pool += ["scroll_feed"] * 5          # Action la plus fréquente
        if remaining["profile_visits"] > 0:
            pool += ["visit_profile"] * 3
        if remaining["stories"] > 0:
            pool += ["view_stories"] * 2
        if remaining["reels"] > 0:
            pool += ["view_reel"] * 2
        if remaining["likes"] > 0:
            pool += ["like_post"] * 2
        if remaining["follows"] > 0:
            pool += ["follow_user"] * 1      # Action la moins fréquente

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
        raw = await scraper.scrape_followers(account, limit=60)
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

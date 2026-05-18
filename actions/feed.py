"""
Défilement naturel du feed Instagram.
"""
import asyncio
import random
from playwright.async_api import Page

from utils.human import scroll_feed, random_sleep, idle_gesture
from utils.logger import get_logger
from storage.database import log_action

logger = get_logger(__name__)


class FeedAction:
    def __init__(self, page: Page):
        self.page = page

    async def scroll(self) -> None:
        """Naviguer vers le feed et défiler naturellement."""
        try:
            current_url = self.page.url
            if "instagram.com/" not in current_url or "instagram.com/p/" in current_url:
                await self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
                await random_sleep(3, 6)

            logger.info("Défilement du feed...")
            await scroll_feed(self.page, times=random.randint(3, 8))

            # Parfois effectuer une action aléatoire d'inactivité
            if random.random() < 0.3:
                await idle_gesture(self.page)

            log_action("scroll_feed", status="success")

        except Exception as e:
            logger.warning(f"Erreur scroll feed : {e}")
            log_action("scroll_feed", status="error", details=str(e))

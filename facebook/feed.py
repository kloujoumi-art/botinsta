import random
from playwright.async_api import Page
from utils.human import random_sleep
from utils.logger import get_logger

logger = get_logger(__name__)


class FbFeedAction:
    def __init__(self, page: Page):
        self.page = page

    async def scroll(self) -> None:
        try:
            if "facebook.com" not in self.page.url:
                await self.page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=25000)
                await random_sleep(2, 4)
            for _ in range(random.randint(3, 7)):
                await self.page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                await random_sleep(1.5, 3.5)
            logger.info("Feed Facebook scrollé ✓")
        except Exception as e:
            logger.warning(f"Erreur scroll feed FB : {e}")

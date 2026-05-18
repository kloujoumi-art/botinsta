"""
Gestionnaire de navigateur Playwright avec techniques anti-détection.
"""
import json
import random
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from core.anti_detection import STEALTH_JS
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.122 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]

VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
    {"width": 1280, "height": 720},
    {"width": 1360, "height": 768},
]

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--lang=fr-FR",
    "--disable-features=IsolateOrigins,site-per-process,VizDisplayCompositor",
    "--disable-ipc-flooding-protection",
    "--disable-background-networking",
    "--disable-client-side-phishing-detection",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-hang-monitor",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-sync",
    "--disable-translate",
    "--metrics-recording-only",
    "--no-default-browser-check",
    "--safebrowsing-disable-auto-update",
    "--password-store=basic",
    "--use-mock-keychain",
    # Réduction mémoire pour Render (512 MB RAM)
    "--renderer-process-limit=1",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--js-flags=--max-old-space-size=192",
    "--disable-audio-output",
    "--mute-audio",
]


class BrowserManager:
    def __init__(self):
        self.settings = get_settings()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.user_agent = random.choice(USER_AGENTS)
        self.viewport = random.choice(VIEWPORTS)

    async def start(self) -> Page:
        self._playwright = await async_playwright().start()

        kwargs: dict = {
            "headless": self.settings.headless,
            "args": LAUNCH_ARGS,
        }

        if self.settings.proxy_url:
            kwargs["proxy"] = {"server": self.settings.proxy_url}

        self._browser = await self._playwright.chromium.launch(**kwargs)

        ctx_kwargs = {
            "viewport": self.viewport,
            "user_agent": self.user_agent,
            "locale": "fr-FR",
            "timezone_id": "Europe/Paris",
            "color_scheme": "light",
            "extra_http_headers": {
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        }

        self._context = await self._browser.new_context(**ctx_kwargs)

        # Anti-détection : injecter le script dans chaque nouvelle page
        await self._context.add_init_script(STEALTH_JS)

        self._page = await self._context.new_page()

        # Masquer d'autres indices automation via CDP
        await self._page.add_init_script(
            "delete Object.getPrototypeOf(navigator).webdriver;"
        )

        logger.info(f"Navigateur démarré — headless={self.settings.headless} | UA: {self.user_agent[:60]}...")
        return self._page

    @property
    def page(self) -> Optional[Page]:
        return self._page

    async def save_cookies(self, filepath: str) -> None:
        if self._context:
            cookies = await self._context.cookies()
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            logger.debug(f"Cookies sauvegardés → {filepath}")

    async def load_cookies(self, filepath: str) -> bool:
        p = Path(filepath)
        if not p.exists():
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            if self._context:
                await self._context.add_cookies(cookies)
            logger.debug(f"Cookies chargés ← {filepath}")
            return True
        except Exception as e:
            logger.warning(f"Impossible de charger les cookies : {e}")
            return False

    async def close(self) -> None:
        for obj in (self._page, self._context, self._browser, self._playwright):
            if obj:
                try:
                    await obj.close()
                except Exception:
                    pass
        logger.info("Navigateur fermé")

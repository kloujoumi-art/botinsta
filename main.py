import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import argparse
import threading

from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


def _start_dashboard(insta_engine=None, fb_engine=None):
    from dashboard.app import run_dashboard, set_bot_engine, set_fb_engine
    if insta_engine:
        set_bot_engine(insta_engine)
    if fb_engine:
        set_fb_engine(fb_engine)
    run_dashboard()


async def run_all(settings, enable_fb: bool):
    from bot.engine import BotEngine
    from dashboard.app import set_bot_engine, set_fb_engine

    insta_engine = BotEngine(settings)
    set_bot_engine(insta_engine)

    fb_engine = None
    if enable_fb:
        from facebook.engine import FbBotEngine
        fb_engine = FbBotEngine()
        set_fb_engine(fb_engine)

    t = threading.Thread(target=_start_dashboard, args=(insta_engine, fb_engine), daemon=True)
    t.start()

    tasks = [asyncio.create_task(insta_engine.run())]
    if fb_engine:
        tasks.append(asyncio.create_task(fb_engine.run()))

    await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser(description="BotInsta + BotFacebook")
    parser.add_argument("--no-facebook", action="store_true", help="Désactiver le bot Facebook")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if args.headless:
        settings.headless = True

    if not settings.instagram_username or not settings.instagram_password:
        print("\n[ERREUR] Configurez INSTAGRAM_USERNAME et INSTAGRAM_PASSWORD dans .env\n")
        sys.exit(1)

    # Activer Facebook si les cookies ou identifiants sont présents
    has_fb = bool(
        os.getenv("FACEBOOK_C_USER") or os.getenv("FACEBOOK_EMAIL")
    )
    enable_fb = has_fb and not args.no_facebook

    logger.info(f"BotInsta démarré — Instagram ✓ | Facebook {'✓' if enable_fb else '✗ (non configuré)'}")
    asyncio.run(run_all(settings, enable_fb))


if __name__ == "__main__":
    main()

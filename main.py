import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""
Point d'entrée principal de BotInsta.

Utilisation :
  python main.py                     → Bot + Dashboard
  python main.py --mode bot          → Bot uniquement
  python main.py --mode dashboard    → Dashboard uniquement
  python main.py --headless          → Mode sans fenêtre de navigateur
"""
import asyncio
import argparse
import threading
import sys

from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


def _start_dashboard(engine=None):
    from dashboard.app import run_dashboard, set_bot_engine
    if engine:
        set_bot_engine(engine)
    run_dashboard()


async def run_bot_only(settings):
    from bot.engine import BotEngine
    engine = BotEngine(settings)
    await engine.run()


async def run_both(settings):
    from bot.engine import BotEngine
    from dashboard.app import set_bot_engine

    engine = BotEngine(settings)
    set_bot_engine(engine)

    # Dashboard dans un thread daemon (s'arrête quand le bot s'arrête)
    t = threading.Thread(target=_start_dashboard, daemon=True)
    t.start()

    await engine.run()


def main():
    parser = argparse.ArgumentParser(
        description="BotInsta — Bot Instagram intelligent et sécurisé",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python main.py                     # Bot + Dashboard (http://127.0.0.1:5000)
  python main.py --mode bot          # Bot uniquement (pas de dashboard)
  python main.py --mode dashboard    # Dashboard uniquement (pas de bot)
  python main.py --headless          # Navigateur sans interface graphique
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["bot", "dashboard", "both"],
        default="both",
        help="Mode de démarrage (défaut: both)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Lancer le navigateur en mode headless (sans fenêtre)",
    )
    args = parser.parse_args()

    settings = get_settings()

    if args.headless:
        settings.headless = True

    # Validation des identifiants
    if args.mode != "dashboard":
        if not settings.instagram_username or not settings.instagram_password:
            print("\n[ERREUR] Configurez INSTAGRAM_USERNAME et INSTAGRAM_PASSWORD dans le fichier .env\n")
            print("Copiez .env.example → .env et remplissez vos identifiants.")
            sys.exit(1)

    if not settings.target_accounts and args.mode != "dashboard":
        print("\n[AVERTISSEMENT] TARGET_ACCOUNTS n'est pas configuré dans .env")
        print("Le bot pourra fonctionner mais ne pourra pas cibler de nouveaux utilisateurs.\n")

    logger.info(f"BotInsta démarré — mode={args.mode} | headless={settings.headless}")
    logger.info(f"Compte : @{settings.instagram_username}")
    if settings.target_accounts:
        logger.info(f"Comptes cibles : {', '.join(settings.target_accounts)}")

    if args.mode == "dashboard":
        _start_dashboard()
    elif args.mode == "bot":
        asyncio.run(run_bot_only(settings))
    else:
        asyncio.run(run_both(settings))


if __name__ == "__main__":
    main()

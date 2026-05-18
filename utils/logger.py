import logging
import sys
from pathlib import Path
from rich.logging import RichHandler
from rich.console import Console

console = Console()
_loggers: dict = {}


def get_logger(name: str) -> logging.Logger:
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)

    if not logger.handlers:
        # Niveau depuis .env (lazy import pour éviter la circularité)
        try:
            from config.settings import get_settings
            level = get_settings().log_level
            log_file = get_settings().log_file
        except Exception:
            level = "INFO"
            log_file = "./data/botinsta.log"

        logger.setLevel(getattr(logging, level, logging.INFO))

        # Console handler (rich)
        rich_handler = RichHandler(
            console=console,
            show_path=False,
            rich_tracebacks=True,
            markup=True,
        )
        rich_handler.setLevel(getattr(logging, level, logging.INFO))
        logger.addHandler(rich_handler)

        # File handler
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)
        except Exception:
            pass

        logger.propagate = False

    _loggers[name] = logger
    return logger

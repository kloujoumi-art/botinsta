import os
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List, Optional

load_dotenv()


@dataclass
class Settings:
    # Credentials
    instagram_username: str = ""
    instagram_password: str = ""

    # Targets
    target_accounts: List[str] = field(default_factory=list)

    # Browser
    headless: bool = False
    proxy_url: Optional[str] = None

    # Daily limits (conservative defaults)
    max_follows_per_day: int = 25
    max_likes_per_day: int = 40
    max_profile_visits_per_day: int = 80
    max_stories_per_day: int = 50
    max_reels_per_day: int = 30

    # Timing (seconds)
    min_action_delay: float = 4.0
    max_action_delay: float = 12.0
    min_session_duration: int = 1800
    max_session_duration: int = 3600

    # Dashboard
    dashboard_port: int = 5000
    dashboard_host: str = "127.0.0.1"

    # Storage
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    sessions_dir: Path = field(default_factory=lambda: Path("./data/sessions"))

    # Logging
    log_level: str = "INFO"
    log_file: str = "./data/botinsta.log"


def _parse_bool(value: str, default: bool = False) -> bool:
    return value.lower() in ("true", "1", "yes") if value else default


def get_settings() -> Settings:
    raw_targets = os.getenv("TARGET_ACCOUNTS", "")
    targets = [t.strip().lstrip("@") for t in raw_targets.split(",") if t.strip()]

    s = Settings(
        instagram_username=os.getenv("INSTAGRAM_USERNAME", ""),
        instagram_password=os.getenv("INSTAGRAM_PASSWORD", ""),
        target_accounts=targets,
        headless=_parse_bool(os.getenv("HEADLESS", "false")),
        proxy_url=os.getenv("PROXY_URL") or None,
        max_follows_per_day=int(os.getenv("MAX_FOLLOWS_PER_DAY", "25")),
        max_likes_per_day=int(os.getenv("MAX_LIKES_PER_DAY", "40")),
        max_profile_visits_per_day=int(os.getenv("MAX_PROFILE_VISITS_PER_DAY", "80")),
        max_stories_per_day=int(os.getenv("MAX_STORIES_PER_DAY", "50")),
        max_reels_per_day=int(os.getenv("MAX_REELS_PER_DAY", "30")),
        min_action_delay=float(os.getenv("MIN_ACTION_DELAY", "4")),
        max_action_delay=float(os.getenv("MAX_ACTION_DELAY", "12")),
        min_session_duration=int(os.getenv("MIN_SESSION_DURATION", "1800")),
        max_session_duration=int(os.getenv("MAX_SESSION_DURATION", "3600")),
        # Render injecte PORT automatiquement — on l'utilise en priorité
        dashboard_port=int(os.getenv("PORT") or os.getenv("DASHBOARD_PORT", "5000")),
        dashboard_host=os.getenv("DASHBOARD_HOST", "127.0.0.1"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("LOG_FILE", "./data/botinsta.log"),
    )

    s.data_dir = Path(os.getenv("DATA_DIR", "./data"))
    s.sessions_dir = Path(os.getenv("SESSIONS_DIR", "./data/sessions"))
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.sessions_dir.mkdir(parents=True, exist_ok=True)

    return s

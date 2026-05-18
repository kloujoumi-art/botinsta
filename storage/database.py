"""
Base de données SQLite : actions, cibles, statistiques journalières, erreurs.
"""
import sqlite3
from pathlib import Path
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

DB_PATH = Path("./data/botinsta.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT    NOT NULL,
    target      TEXT,
    status      TEXT    NOT NULL DEFAULT 'success',
    details     TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS targets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT UNIQUE NOT NULL,
    source       TEXT,
    status       TEXT DEFAULT 'pending',
    is_private   INTEGER DEFAULT 0,
    follower_count INTEGER,
    added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT UNIQUE NOT NULL,
    follows         INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    profile_visits  INTEGER DEFAULT 0,
    stories_viewed  INTEGER DEFAULT 0,
    reels_viewed    INTEGER DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type  TEXT,
    message     TEXT,
    action_type TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_actions_created ON actions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_targets_status  ON targets(status);
CREATE INDEX IF NOT EXISTS idx_errors_created  ON errors(created_at DESC);
"""


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(_SCHEMA)


# ── Actions ─────────────────────────────────────────────────────────────────

def log_action(action_type: str, target: str = None, status: str = "success", details: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO actions (action_type, target, status, details) VALUES (?, ?, ?, ?)",
            (action_type, target, status, details),
        )


def get_recent_actions(limit: int = 100) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM actions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Statistiques journalières ────────────────────────────────────────────────

def get_today_stats() -> Dict[str, Any]:
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM daily_stats WHERE date = ?", (today,)
        ).fetchone()
        if row:
            return dict(row)
        return {
            "date": today,
            "follows": 0,
            "likes": 0,
            "profile_visits": 0,
            "stories_viewed": 0,
            "reels_viewed": 0,
        }


def increment_stat(stat_name: str, amount: int = 1) -> None:
    today = date.today().isoformat()
    with get_db() as conn:
        conn.execute(
            f"""
            INSERT INTO daily_stats (date, {stat_name})
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET
                {stat_name} = {stat_name} + ?,
                updated_at  = CURRENT_TIMESTAMP
            """,
            (today, amount, amount),
        )


def get_weekly_stats() -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT 7"
        ).fetchall()
        return [dict(r) for r in rows]


# ── Cibles ───────────────────────────────────────────────────────────────────

def add_target(username: str, source: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO targets (username, source) VALUES (?, ?)",
            (username, source),
        )


def add_targets_bulk(usernames: List[str], source: str = None) -> int:
    added = 0
    with get_db() as conn:
        for u in usernames:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO targets (username, source) VALUES (?, ?)", (u, source)
            )
            added += cursor.rowcount
    return added


def get_pending_targets(limit: int = 50) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM targets WHERE status = 'pending' ORDER BY added_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_target_status(username: str, status: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE targets SET status = ?, processed_at = CURRENT_TIMESTAMP WHERE username = ?",
            (status, username),
        )


def is_already_targeted(username: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM targets WHERE username = ?", (username,)
        ).fetchone()
        return row is not None


def get_targets_summary() -> Dict[str, int]:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='pending'  THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status='followed' THEN 1 ELSE 0 END) AS followed,
                SUM(CASE WHEN status='skipped'  THEN 1 ELSE 0 END) AS skipped,
                SUM(CASE WHEN status='visited'  THEN 1 ELSE 0 END) AS visited
            FROM targets
            """
        ).fetchone()
        return dict(row) if row else {}


# ── Erreurs ──────────────────────────────────────────────────────────────────

def log_error(error_type: str, message: str, action_type: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO errors (error_type, message, action_type) VALUES (?, ?, ?)",
            (error_type, str(message)[:500], action_type),
        )


def get_recent_errors(limit: int = 50) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM errors ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

"""
Tables Facebook dans la même base SQLite que botinsta.
Toutes les tables sont préfixées fb_ pour éviter les conflits.
"""
import sqlite3
import os
from pathlib import Path
from datetime import date
from typing import List, Dict, Any
from contextlib import contextmanager

DB_PATH = Path(os.getenv("DATA_DIR", "./data")) / "botinsta.db"

_FB_SCHEMA = """
CREATE TABLE IF NOT EXISTS fb_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT    NOT NULL,
    target      TEXT,
    status      TEXT    NOT NULL DEFAULT 'success',
    details     TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fb_targets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT,
    profile_url  TEXT UNIQUE NOT NULL,
    source       TEXT,
    status       TEXT DEFAULT 'pending',
    added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fb_daily_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT UNIQUE NOT NULL,
    friend_requests INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    stories_viewed  INTEGER DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fb_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type  TEXT,
    message     TEXT,
    action_type TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fb_actions_created ON fb_actions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fb_targets_status  ON fb_targets(status);
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


def fb_init_db() -> None:
    with get_db() as conn:
        conn.executescript(_FB_SCHEMA)


# ── Actions ──────────────────────────────────────────────────────────────────

def fb_log_action(action_type: str, target: str = None, status: str = "success", details: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO fb_actions (action_type, target, status, details) VALUES (?, ?, ?, ?)",
            (action_type, target, status, details),
        )


def fb_get_recent_actions(limit: int = 100) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fb_actions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Stats ────────────────────────────────────────────────────────────────────

def fb_get_today_stats() -> Dict[str, Any]:
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM fb_daily_stats WHERE date = ?", (today,)).fetchone()
        if row:
            return dict(row)
        return {"date": today, "friend_requests": 0, "likes": 0, "stories_viewed": 0}


def fb_increment_stat(stat_name: str, amount: int = 1) -> None:
    today = date.today().isoformat()
    with get_db() as conn:
        conn.execute(
            f"""
            INSERT INTO fb_daily_stats (date, {stat_name})
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET
                {stat_name} = {stat_name} + ?,
                updated_at  = CURRENT_TIMESTAMP
            """,
            (today, amount, amount),
        )


# ── Cibles ───────────────────────────────────────────────────────────────────

def fb_add_targets_bulk(targets: List[Dict], source: str = None) -> int:
    added = 0
    with get_db() as conn:
        for t in targets:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO fb_targets (name, profile_url, source) VALUES (?, ?, ?)",
                (t.get("name"), t["profile_url"], source),
            )
            added += cursor.rowcount
    return added


def fb_get_pending_targets(limit: int = 50) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fb_targets WHERE status = 'pending' ORDER BY added_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def fb_update_target_status(profile_url: str, status: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE fb_targets SET status = ?, processed_at = CURRENT_TIMESTAMP WHERE profile_url = ?",
            (status, profile_url),
        )


def fb_is_already_targeted(profile_url: str) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM fb_targets WHERE profile_url = ?", (profile_url,)).fetchone()
        return row is not None


def fb_get_targets_summary() -> Dict[str, int]:
    with get_db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS total,
               SUM(CASE WHEN status='pending'      THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN status='friend_added' THEN 1 ELSE 0 END) AS friend_added,
               SUM(CASE WHEN status='skipped'      THEN 1 ELSE 0 END) AS skipped
               FROM fb_targets"""
        ).fetchone()
        return dict(row) if row else {}


def fb_get_friend_added(limit: int = 200) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name, profile_url, processed_at FROM fb_targets WHERE status='friend_added' ORDER BY processed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Erreurs ──────────────────────────────────────────────────────────────────

def fb_log_error(error_type: str, message: str, action_type: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO fb_errors (error_type, message, action_type) VALUES (?, ?, ?)",
            (error_type, str(message)[:500], action_type),
        )


def fb_get_recent_errors(limit: int = 50) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fb_errors ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

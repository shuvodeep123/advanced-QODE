"""
chat_history.py — SQLite-backed persistent chat history for advanced-QODE.

Messages are stored per session so the conversation survives Streamlit page
refreshes, browser tab closures, and server hot-reloads during the same OS
session.

Schema
------
    sessions(session_id TEXT PK, created_at TEXT)

    messages(id INTEGER PK AUTOINCREMENT,
             session_id TEXT FK → sessions,
             role TEXT,           -- "user" | "assistant"
             content TEXT,
             mode TEXT,           -- "asis" | "principles" | "error"
             diagram_path TEXT,
             diagram_type TEXT,
             eval_score REAL,
             extra TEXT,          -- JSON blob for any extra keys
             created_at TEXT)

Public API
----------
    new_session_id()            → str          — fresh UUID
    ensure_session(session_id)  → None         — upsert session row
    save_message(session_id, msg_dict)          — persist one message
    load_history(session_id)    → list[dict]   — messages in order
    list_sessions(hours=96)     → list[dict]   — all sessions in last 96 h
    clear_session(session_id)   → None         — delete all messages
    prune_old_sessions(days=4)  → int          — housekeeping (96 h default)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_PATH = Path("./chat_history.db")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent Streamlit reruns
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT    NOT NULL REFERENCES sessions(session_id)
                                              ON DELETE CASCADE,
                role         TEXT    NOT NULL,
                content      TEXT    NOT NULL DEFAULT '',
                mode         TEXT,
                diagram_path TEXT,
                diagram_type TEXT,
                eval_score   REAL,
                extra        TEXT,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_session "
            "ON messages(session_id, id)"
        )
        conn.commit()


# Initialise schema once at import time
_init_db()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def new_session_id() -> str:
    """Return a fresh random session UUID string."""
    return str(uuid.uuid4())


def ensure_session(session_id: str) -> None:
    """Create the session row if it does not already exist."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions(session_id, created_at) VALUES (?, ?)",
            (session_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def save_message(session_id: str, msg: dict[str, Any]) -> None:
    """Persist one message dict to the database.

    Standard keys (role, content, mode, diagram_path, diagram_type,
    eval_score) are stored in dedicated columns; anything else goes into
    the JSON ``extra`` blob.
    """
    ensure_session(session_id)
    _KNOWN = {"role", "content", "mode", "diagram_path", "diagram_type", "eval_score"}
    extra = {k: v for k, v in msg.items() if k not in _KNOWN}

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO messages
                (session_id, role, content, mode,
                 diagram_path, diagram_type, eval_score, extra, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                msg.get("role", ""),
                msg.get("content", ""),
                msg.get("mode"),
                msg.get("diagram_path"),
                msg.get("diagram_type"),
                msg.get("eval_score"),
                json.dumps(extra) if extra else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def load_history(session_id: str) -> list[dict[str, Any]]:
    """Return all messages for *session_id* in insertion order."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        msg: dict[str, Any] = {
            "role":    row["role"],
            "content": row["content"],
        }
        for col in ("mode", "diagram_path", "diagram_type"):
            if row[col] is not None:
                msg[col] = row[col]
        if row["eval_score"] is not None:
            msg["eval_score"] = row["eval_score"]
        if row["extra"]:
            try:
                msg.update(json.loads(row["extra"]))
            except Exception:
                pass
        result.append(msg)
    return result


def clear_session(session_id: str) -> None:
    """Delete all messages for *session_id*."""
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
    logger.info("Chat history cleared for session %s", session_id)


def list_sessions(hours: int = 96) -> list[dict[str, Any]]:
    """Return all sessions created within the last *hours* hours, newest first.

    Each entry contains:
      - session_id     : str
      - created_at     : ISO-8601 UTC string
      - first_message  : first user message (up to 80 chars), or "(empty)"
      - message_count  : total messages in the session
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.session_id,
                   s.created_at,
                   (SELECT content FROM messages
                    WHERE session_id = s.session_id AND role = 'user'
                    ORDER BY id LIMIT 1) AS first_message,
                   COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            WHERE s.created_at >= ?
            GROUP BY s.session_id
            ORDER BY s.created_at DESC
            """,
            (cutoff,),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        fm = row["first_message"] or "(empty)"
        result.append({
            "session_id":    row["session_id"],
            "created_at":    row["created_at"],
            "first_message": fm[:80] + ("…" if len(fm) > 80 else ""),
            "message_count": row["message_count"] or 0,
        })
    return result


def prune_old_sessions(days: int = 4) -> int:
    """Delete sessions (and their messages) older than *days* days (default 4 = 96 h).

    Returns the number of sessions pruned.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _connect() as conn:
        old = conn.execute(
            "SELECT session_id FROM sessions WHERE created_at < ?", (cutoff,)
        ).fetchall()
        if not old:
            return 0
        ids = [r["session_id"] for r in old]
        ph  = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM messages WHERE session_id IN ({ph})", ids)
        conn.execute(f"DELETE FROM sessions  WHERE session_id IN ({ph})", ids)
        conn.commit()
        logger.info("Pruned %d old sessions (older than %d days)", len(ids), days)
        return len(ids)

"""
db.py — SQLite persistence layer for CuBot.

Schema
------
members(qid PK, name, extra_id)
attempts(id PK, qid FK, scope, project, seconds, recorded_at)

The `scope` column isolates datasets: 'daily' for the regular club
scoreboard, 'compYY' for competitions (e.g., 'comp24'), and any future named
competitions just use their own scope string.
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime

_DB_PATH: Path = None

# --------------------------------------------------------------------------- #
#  Connection & schema                                                          #
# --------------------------------------------------------------------------- #

def _connect() -> sqlite3.Connection:
    """Open a WAL-mode connection with Row factory enabled."""
    if _DB_PATH is None:
        raise RuntimeError("Database not initialized. Call init_db(db_path) first.")
        
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    """Create tables and indexes if they do not yet exist. Call once at startup."""
    global _DB_PATH
    _DB_PATH = db_path
    
    conn = _connect()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS members (
                qid      TEXT PRIMARY KEY,
                name     TEXT NOT NULL,
                extra_id TEXT
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                qid         TEXT NOT NULL REFERENCES members(qid) ON DELETE CASCADE,
                scope       TEXT NOT NULL,
                project     TEXT NOT NULL,
                seconds     REAL NOT NULL,
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_attempts_qid_scope_project
                ON attempts (qid, scope, project);

            CREATE INDEX IF NOT EXISTS idx_attempts_scope_project_date
                ON attempts (scope, project, recorded_at);
        """)
    conn.close()


# --------------------------------------------------------------------------- #
#  Members                                                                     #
# --------------------------------------------------------------------------- #

def upsert_member(qid: str, name: str, extra_id: str = None) -> None:
    """Insert or update a member record."""
    conn = _connect()
    with conn:
        conn.execute(
            """
            INSERT INTO members (qid, name, extra_id) VALUES (?, ?, ?)
            ON CONFLICT(qid) DO UPDATE SET name = excluded.name,
                                           extra_id = excluded.extra_id
            """,
            (qid, name, extra_id),
        )
    conn.close()


def delete_member(qid: str) -> None:
    """Delete a member and all their attempts (cascade)."""
    conn = _connect()
    with conn:
        conn.execute("DELETE FROM members WHERE qid = ?", (qid,))
    conn.close()


def get_member_by_qid(qid: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM members WHERE qid = ?", (qid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_members() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM members ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_name_by_qid(qid: str) -> str:
    """Return display name or '未绑定' if not found."""
    row = get_member_by_qid(qid)
    return row["name"] if row else "未绑定"


def get_qid_by_name(name: str) -> str:
    """Return qid or '未绑定' if not found."""
    conn = _connect()
    row = conn.execute("SELECT qid FROM members WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row["qid"] if row else "未绑定"


def member_exists(qid: str) -> bool:
    return get_member_by_qid(qid) is not None


# --------------------------------------------------------------------------- #
#  Attempts                                                                    #
# --------------------------------------------------------------------------- #

def insert_attempt(
    qid: str,
    scope: str,
    project: str,
    seconds: float,
    recorded_at: str | None = None,
) -> None:
    """Append a single attempt. `recorded_at` defaults to now (ISO-8601)."""
    if recorded_at is None:
        recorded_at = datetime.now().isoformat()
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO attempts (qid, scope, project, seconds, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (qid, scope, project, seconds, recorded_at),
        )
    conn.close()


def get_attempts(qid: str, scope: str, project: str) -> list[float]:
    """Return all attempt times (seconds) for a member in submission order."""
    conn = _connect()
    rows = conn.execute(
        "SELECT seconds FROM attempts WHERE qid = ? AND scope = ? AND project = ? ORDER BY id",
        (qid, scope, project),
    ).fetchall()
    conn.close()
    return [r["seconds"] for r in rows]


def get_attempts_in_period(
    qid: str, scope: str, project: str, period: str
) -> list[float]:
    """
    Return attempts within the *current* calendar period.

    period: 'day' | 'month' | 'year'
    """
    now = datetime.now()
    if period == "day":
        date_filter = now.strftime("%Y-%m-%d")
        fmt = "%Y-%m-%d"
    elif period == "month":
        date_filter = now.strftime("%Y-%m")
        fmt = "%Y-%m"
    else:  # year
        date_filter = now.strftime("%Y")
        fmt = "%Y"
    conn = _connect()
    rows = conn.execute(
        f"SELECT seconds FROM attempts "
        f"WHERE qid=? AND scope=? AND project=? AND strftime('{fmt}', recorded_at)=? "
        f"ORDER BY id",
        (qid, scope, project, date_filter),
    ).fetchall()
    conn.close()
    return [r["seconds"] for r in rows]


def get_all_qids_for_scope(scope: str) -> list[str]:
    """Return every qid that has at least one attempt in the given scope."""
    conn = _connect()
    rows = conn.execute(
        "SELECT DISTINCT qid FROM attempts WHERE scope = ?", (scope,)
    ).fetchall()
    conn.close()
    return [r["qid"] for r in rows]


def get_project_count_by_scope(scope: str) -> dict[str, int]:
    """Return {qid: num_distinct_projects} for all members in the scope."""
    conn = _connect()
    rows = conn.execute(
        "SELECT qid, COUNT(DISTINCT project) AS cnt FROM attempts WHERE scope = ? GROUP BY qid",
        (scope,),
    ).fetchall()
    conn.close()
    return {r["qid"]: r["cnt"] for r in rows}

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
        _create_tables(conn)
    conn.close()


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            student_id TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            qid        TEXT UNIQUE,
            extra_id   TEXT
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  TEXT NOT NULL REFERENCES members(student_id) ON DELETE CASCADE ON UPDATE CASCADE,
            scope       TEXT NOT NULL,
            project     TEXT NOT NULL,
            seconds     REAL NOT NULL,
            recorded_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_attempts_sid_scope_project
            ON attempts (student_id, scope, project);

        CREATE INDEX IF NOT EXISTS idx_attempts_scope_project_date
            ON attempts (scope, project, recorded_at);
            
        CREATE INDEX IF NOT EXISTS idx_members_name
            ON members (name);
    """)


# --------------------------------------------------------------------------- #
#  Members                                                                     #
# --------------------------------------------------------------------------- #

def upsert_member(student_id: str, name: str, qid: str = None, extra_id: str = None) -> None:
    """Insert or update a member record."""
    conn = _connect()
    with conn:
        conn.execute(
            """
            INSERT INTO members (student_id, name, qid, extra_id) VALUES (?, ?, ?, ?)
            ON CONFLICT(student_id) DO UPDATE SET 
                name = excluded.name,
                qid = COALESCE(excluded.qid, members.qid),
                extra_id = COALESCE(excluded.extra_id, members.extra_id)
            """,
            (student_id, name, qid, extra_id),
        )
    conn.close()

def update_member_extra(student_id: str, extra_id: str) -> None:
    conn = _connect()
    with conn:
        conn.execute("UPDATE members SET extra_id = ? WHERE student_id = ?", (extra_id, student_id))
    conn.close()

def bind_qid(qid: str, student_id: str, new_sid: str = None) -> bool:
    """
    Bind a QID to a student_id. 
    If new_sid is provided, update the member's ID in both members and attempts tables.
    """
    conn = _connect()
    with conn:
        # Check if qid is already bound to someone else
        existing = conn.execute("SELECT student_id FROM members WHERE qid = ?", (qid,)).fetchone()
        if existing and existing['student_id'] != (new_sid or student_id):
            conn.close()
            return False # Already bound
            
        if new_sid:
            # Update members table. ON UPDATE CASCADE will handle the attempts table.
            conn.execute("UPDATE members SET student_id = ?, qid = ? WHERE student_id = ?", (new_sid, qid, student_id))
        else:
            conn.execute("UPDATE members SET qid = ? WHERE student_id = ?", (qid, student_id))
    conn.close()
    return True



def unbind_qid(student_id: str) -> None:
    conn = _connect()
    with conn:
        conn.execute("UPDATE members SET qid = NULL WHERE student_id = ?", (student_id,))
    conn.close()

def delete_member(student_id: str) -> None:
    """Delete a member and all their attempts (cascade)."""
    conn = _connect()
    with conn:
        conn.execute("DELETE FROM members WHERE student_id = ?", (student_id,))
    conn.close()


def get_member_by_sid(student_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM members WHERE student_id = ?", (student_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_member_by_qid(qid: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM members WHERE qid = ?", (qid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_members_by_name(name: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM members WHERE name = ?", (name,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_members() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM members ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_name_collision_map() -> dict[str, int]:
    """Return {name: count} for all members to detect collisions."""
    conn = _connect()
    rows = conn.execute("SELECT name, COUNT(*) as cnt FROM members GROUP BY name").fetchall()
    conn.close()
    return {r["name"]: r["cnt"] for r in rows}

def get_name_by_qid(qid: str) -> str:
    row = get_member_by_qid(qid)
    return row["name"] if row else "未绑定"

def get_sid_by_qid(qid: str) -> str | None:
    row = get_member_by_qid(qid)
    return row["student_id"] if row else None

def member_exists(student_id: str) -> bool:
    return get_member_by_sid(student_id) is not None


# --------------------------------------------------------------------------- #
#  Attempts                                                                    #
# --------------------------------------------------------------------------- #

def insert_attempt(
    student_id: str,
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
            "INSERT INTO attempts (student_id, scope, project, seconds, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (student_id, scope, project, seconds, recorded_at),
        )
    conn.close()


def delete_last_batch(student_id: str, scope: str) -> list[dict]:
    """Delete all attempts from the latest recorded batch for this user."""
    conn = _connect()
    with conn:
        # Find latest timestamp
        res = conn.execute(
            "SELECT recorded_at FROM attempts WHERE student_id = ? AND scope = ? ORDER BY recorded_at DESC LIMIT 1",
            (student_id, scope)
        ).fetchone()
        if not res:
            conn.close()
            return []
        
        last_ts = res['recorded_at']
        # Get details before delete
        rows = conn.execute(
            "SELECT project, seconds FROM attempts WHERE student_id = ? AND scope = ? AND recorded_at = ?",
            (student_id, scope, last_ts)
        ).fetchall()
        deleted = [dict(r) for r in rows]
        
        # Delete
        conn.execute(
            "DELETE FROM attempts WHERE student_id = ? AND scope = ? AND recorded_at = ?",
            (student_id, scope, last_ts)
        )
    conn.close()
    return deleted


def get_attempts(student_id: str, scope: str, project: str) -> list[float]:
    """Return all attempt times (seconds) for a member in submission order."""
    conn = _connect()
    rows = conn.execute(
        "SELECT seconds FROM attempts WHERE student_id = ? AND scope = ? AND project = ? ORDER BY id",
        (student_id, scope, project),
    ).fetchall()
    conn.close()
    return [r["seconds"] for r in rows]


def get_attempts_in_period(
    student_id: str, scope: str, project: str, period: str
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
        f"WHERE student_id=? AND scope=? AND project=? AND strftime('{fmt}', recorded_at)=? "
        f"ORDER BY id",
        (student_id, scope, project, date_filter),
    ).fetchall()
    conn.close()
    return [r["seconds"] for r in rows]


def get_all_sids_for_scope(scope: str) -> list[str]:
    """Return every student_id that has at least one attempt in the given scope."""
    conn = _connect()
    rows = conn.execute(
        "SELECT DISTINCT student_id FROM attempts WHERE scope = ?", (scope,)
    ).fetchall()
    conn.close()
    return [r["student_id"] for r in rows]


def get_project_count_by_scope(scope: str) -> dict[str, int]:
    """Return {student_id: num_distinct_projects} for all members in the scope."""
    conn = _connect()
    rows = conn.execute(
        "SELECT student_id, COUNT(DISTINCT project) AS cnt FROM attempts WHERE scope = ? GROUP BY student_id",
        (scope,),
    ).fetchall()
    conn.close()
    return {r["student_id"]: r["cnt"] for r in rows}


def get_project_count_all_scopes() -> dict[str, int]:
    """Return {student_id: num_distinct_projects} across all scopes."""
    conn = _connect()
    rows = conn.execute(
        "SELECT student_id, COUNT(DISTINCT project) AS cnt FROM attempts GROUP BY student_id"
    ).fetchall()
    conn.close()
    return {r["student_id"]: r["cnt"] for r in rows}


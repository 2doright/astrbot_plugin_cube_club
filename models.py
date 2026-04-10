"""
models.py — Member domain model and score computation.

Score computation is purely functional (operates on list[float]),
with no in-memory state. All persistence goes through storage.db.
"""

from .constants import MO3_PROJECTS
from .time_utils import TimeConvert
from . import db


# --------------------------------------------------------------------------- #
#  Pure score computation helpers                                               #
# --------------------------------------------------------------------------- #

def _best_rolling_avg(attempts: list[float], window: int) -> float | None:
    """Return the minimum average across all consecutive windows of `window` size."""
    if len(attempts) < window:
        return None
    best = None
    for i in range(len(attempts) - window + 1):
        avg = round(sum(attempts[i : i + window]) / window, 3)
        if best is None or avg < best:
            best = avg
    return best


def _current_avg(attempts: list[float], window: int) -> float | None:
    """Return the average of the most recent `window` attempts."""
    if len(attempts) < window:
        return None
    return round(sum(attempts[-window:]) / window, 3)


def compute_display_stats(attempts: list[float], project: str) -> dict:
    """
    Stats for personal queries (ask / askother).

    Returns:
        pb       — personal best (min)
        cur_avg  — current ao5 or mo3 (latest window), or None
        aoAll    — running mean of all attempts
        label    — 'ao5' or 'mo3'
    """
    if not attempts:
        return {"pb": None, "cur_avg": None, "aoAll": None, "label": "ao5"}
    window = 3 if project in MO3_PROJECTS else 5
    label = "mo3" if project in MO3_PROJECTS else "ao5"
    return {
        "pb": round(min(attempts), 3),
        "cur_avg": _current_avg(attempts, window),
        "aoAll": round(sum(attempts) / len(attempts), 3),
        "label": label,
    }


def compute_rank_stats(attempts: list[float], project: str) -> dict:
    """
    Stats for leaderboard queries (rank).

    pb and best_avg use the BEST value across all submissions
    so they match the original rank behaviour.
    aoAll is always the running mean (latest value).
    """
    if not attempts:
        return {"pb": None, "best_avg": None, "aoAll": None}
    window = 3 if project in MO3_PROJECTS else 5
    return {
        "pb": round(min(attempts), 3),
        "best_avg": _best_rolling_avg(attempts, window),
        "aoAll": round(sum(attempts) / len(attempts), 3),
    }


# --------------------------------------------------------------------------- #
#  Member                                                                      #
# --------------------------------------------------------------------------- #

class Member:
    """
    Lightweight facade over the storage layer.

    All class methods are stateless — they fetch/persist data on each call.
    The `scope` parameter separates 'daily' club data from named competitions
    such as 'comp24'.
    """

    # ---- Identity --------------------------------------------------------- #

    @staticmethod
    def create(name: str, qid: str, extra_id: str = None) -> None:
        """Register a new member (or update existing)."""
        db.upsert_member(qid, name, extra_id)

    @staticmethod
    def delete(qid: str) -> bool:
        """Delete a member and all their data. Returns False if not found."""
        if not db.member_exists(qid):
            return False
        db.delete_member(qid)
        return True

    @staticmethod
    def exists(qid: str) -> bool:
        return db.member_exists(qid)

    @staticmethod
    def get_name_by_qid(qid: str) -> str:
        """Return display name or '未绑定'."""
        return db.get_name_by_qid(qid)

    @staticmethod
    def get_qid_by_name(name: str) -> str:
        """Return qid or '未绑定'."""
        return db.get_qid_by_name(name)

    # ---- Scores ----------------------------------------------------------- #

    @staticmethod
    def upload_score(qid: str, scope: str, project: str, score_text: str) -> None:
        """
        Parse space-separated time strings from `score_text` and insert each
        as an attempt. Tokens that parse to 0.0 are silently skipped.
        """
        tokens = [t for t in score_text.split() if t]
        for token in tokens:
            seconds = TimeConvert.time_to_seconds(token)
            if seconds != 0.0:
                db.insert_attempt(qid, scope, project, round(seconds, 3))

    @staticmethod
    def ask_score(qid: str, scope: str, project: str) -> str:
        """Return a formatted string with pb / ao5(mo3) / aoAll for the member."""
        attempts = db.get_attempts(qid, scope, project)
        stats = compute_display_stats(attempts, project)
        tc = TimeConvert.seconds_to_time
        label = stats["label"]
        return (
            f"pb {tc(stats['pb'])}\n"
            f"{label}(当前) {tc(stats['cur_avg'])}\n"
            f"aoAll {tc(stats['aoAll'])}"
        )

    @staticmethod
    def ask_all_scores(qid: str, scope: str) -> str:
        """Return a summary of every project with at least one attempt."""
        from .constants import ALL_PROJECT_TYPES
        lines = []
        for project in ALL_PROJECT_TYPES:
            attempts = db.get_attempts(qid, scope, project)
            if attempts:
                stats = compute_display_stats(attempts, project)
                tc = TimeConvert.seconds_to_time
                lines.append(
                    f"{project}: pb {tc(stats['pb'])}  {stats['label']} {tc(stats['cur_avg'])}"
                )
        return "\n".join(lines) if lines else "暂无成绩"

    @staticmethod
    def count_projects(qid: str, scope: str) -> int:
        """Return the number of distinct projects the member has attempted."""
        counts = db.get_project_count_by_scope(scope)
        return counts.get(qid, 0)

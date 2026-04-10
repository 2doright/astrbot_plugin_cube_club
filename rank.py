"""
rank.py — Live rank computation from the attempts table.

No snapshot files are written. All rankings are computed on demand by
querying the attempts table and computing stats in Python.
Supported rank types:
  'day' | 'month' | 'year' — filter to current calendar period
  'alltime'                — no time filter
  'count'                  — rank by number of distinct projects attempted
"""

from .constants import ALL_PROJECT_TYPES, MO3_PROJECTS
from .time_utils import TimeConvert
from .models import compute_rank_stats
from . import db


class RankQuery:
    @staticmethod
    def get_rank_list(
        scope: str,
        rank_type: str,
        project: str = None,
        statistic: str = None,
    ) -> str:
        """
        Build a formatted leaderboard string.

        Parameters
        ----------
        scope     : 'daily' | 'compYY' | any competition scope string
        rank_type : 'day' | 'month' | 'year' | 'alltime' | 'count'
        project   : project name (required unless rank_type == 'count')
        statistic : 'pb' | 'ao5/mo3' | 'aoAll' (required unless rank_type == 'count')
        """
        if rank_type == "count":
            return RankQuery._count_rank(scope)
        return RankQuery._time_rank(scope, rank_type, project, statistic)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_period_attempts(
        qid: str, scope: str, project: str, rank_type: str
    ) -> list[float]:
        """Fetch attempts for a member filtered by the given time period."""
        if rank_type in ("day", "month", "year"):
            return db.get_attempts_in_period(qid, scope, project, rank_type)
        # alltime — no filter
        return db.get_attempts(qid, scope, project)

    @staticmethod
    def _time_rank(
        scope: str, rank_type: str, project: str, statistic: str
    ) -> str:
        """Leaderboard for a specific project + statistic within a time period."""
        header = f"{rank_type}-Rank\n{project} {statistic}\n"
        scores: dict[str, float] = {}

        for qid in db.get_all_qids_for_scope(scope):
            attempts = RankQuery._get_period_attempts(qid, scope, project, rank_type)
            if not attempts:
                continue
            stats = compute_rank_stats(attempts, project)

            # Map statistic key → value
            if statistic == "pb":
                value = stats["pb"]
            elif statistic == "ao5/mo3":
                value = stats["best_avg"]
            else:  # aoAll
                value = stats["aoAll"]

            if value is None:
                continue

            name = db.get_name_by_qid(qid)
            scores[name] = value

        if not scores:
            return header + "（暂无数据）\n"

        ranked = sorted(scores.items(), key=lambda x: x[1])
        max_len = max(len(n) for n, _ in ranked)
        lines = [
            f"{name:<{max_len}} | {TimeConvert.seconds_to_time(val)}"
            for name, val in ranked
        ]
        return header + "\n".join(lines) + "\n"

    @staticmethod
    def _count_rank(scope: str) -> str:
        """Leaderboard ordered by number of distinct projects attempted."""
        header = "count-Rank\n"
        project_counts = db.get_project_count_by_scope(scope)

        if not project_counts:
            return header + "（暂无数据）\n"

        named: dict[str, int] = {}
        for qid, cnt in project_counts.items():
            named[db.get_name_by_qid(qid)] = cnt

        ranked = sorted(named.items(), key=lambda x: x[1], reverse=True)
        max_len = max(len(n) for n, _ in ranked)
        lines = [f"{name:<{max_len}} | {cnt}" for name, cnt in ranked]
        return header + "\n".join(lines) + "\n"

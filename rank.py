from .constants import MO3_PROJECTS
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
        """
        data = RankQuery.get_rank_data(scope, rank_type, project, statistic)
        header = data["header"]
        if not data["results"]:
            return header + "（暂无数据）\n"

        lines = [
            f"{i+1}. {r['name']} | {r['value_display']}"
            for i, r in enumerate(data["results"])
        ]
        return header + "\n".join(lines) + "\n"

    @staticmethod
    def get_rank_data(
        scope: str,
        rank_type: str,
        project: str = None,
        statistic: str = None,
    ) -> dict:
        """
        Fetch leaderboard data as a structured dictionary.
        """
        if rank_type == "count":
            return RankQuery._count_rank_data(scope)
        return RankQuery._time_rank_data(scope, rank_type, project, statistic)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_period_attempts(
        sid: str, scope: str, project: str, rank_type: str
    ) -> list[float]:
        """Fetch attempts for a member filtered by the given time period."""
        if rank_type in ("day", "month", "year"):
            return db.get_attempts_in_period(sid, scope, project, rank_type)
        return db.get_attempts(sid, scope, project)

    @staticmethod
    def _time_rank_data(
        scope: str, rank_type: str, project: str, statistic: str
    ) -> dict:
        header = f"{rank_type}-Rank\n{project} {statistic}\n"
        results: list[dict] = []

        all_sids = db.get_all_sids_for_scope(scope)
        collision_map = db.get_name_collision_map()
        for sid in all_sids:
            attempts = RankQuery._get_period_attempts(sid, scope, project, rank_type)
            if not attempts:
                continue
            stats = compute_rank_stats(attempts, project)

            if statistic == "pb":
                value = stats["pb"]
            elif statistic == "ao5/mo3":
                value = stats["best_avg"]
            else:  # aoAll
                value = stats["aoAll"]

            if value is None or value >= TimeConvert.DNF_VALUE:
                continue

            member = db.get_member_by_sid(sid)
            extra_id = member.get('extra_id')
            
            if extra_id:
                name_display = extra_id
            else:
                name = member['name']
                if collision_map.get(name, 0) > 1:
                    name_display = f"{name}[*{sid[-4:]}]"
                else:
                    name_display = name
            
            results.append({
                "name": name_display, 
                "value": value, 
                "value_display": TimeConvert.seconds_to_time(value)
            })

        ranked = sorted(results, key=lambda x: x["value"])
        for i, r in enumerate(ranked):
            r["rank"] = i + 1

        return {
            "title": f"{rank_type.upper()} RANK",
            "subtitle": f"{project} {statistic}",
            "header": header,
            "results": ranked
        }

    @staticmethod
    def _count_rank_data(scope: str) -> dict:
        header = "count-Rank\n"
        project_counts = db.get_project_count_by_scope(scope)

        if not project_counts:
            return {
                "title": "COUNT RANK",
                "subtitle": "Project Variety",
                "header": header,
                "results": []
            }

        results: list[dict] = []
        collision_map = db.get_name_collision_map()
        for sid, cnt in project_counts.items():
            member = db.get_member_by_sid(sid)
            extra_id = member.get('extra_id') if member else None
            
            if extra_id:
                name_display = extra_id
            else:
                name = member['name'] if member else "未知"
                if collision_map.get(name, 0) > 1:
                    name_display = f"{name}[*{sid[-4:]}]"
                else:
                    name_display = name
            results.append({
                "name": name_display, 
                "cnt": cnt, 
                "value": -cnt, # for sorting
                "value_display": str(cnt)
            })

        ranked = sorted(results, key=lambda x: x["cnt"], reverse=True)
        for i, r in enumerate(ranked):
            r["rank"] = i + 1

        return {
            "title": "COUNT RANK",
            "subtitle": "Project Variety",
            "header": header,
            "results": ranked
        }


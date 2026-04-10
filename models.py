from .constants import MO3_PROJECTS
from .time_utils import TimeConvert
from . import db


# --------------------------------------------------------------------------- #
#  Pure score computation helpers                                               #
# --------------------------------------------------------------------------- #

def _wca_avg(attempts: list[float], project: str) -> float | None:
    """Calculate WCA-standard average (ao5 or mo3)."""
    if project in MO3_PROJECTS:
        return _wca_mo3(attempts)
    return _wca_ao5(attempts)


def _wca_ao5(attempts: list[float]) -> float | None:
    """Average of 5 (WCA): Trim best and worst, average remaining 3."""
    if len(attempts) < 5:
        return None
    window = attempts[-5:]
    dnf_val = TimeConvert.DNF_VALUE
    
    # Sort window
    sorted_window = sorted(window)
    
    # If 2 or more DNFs, return DNF
    dnf_count = sum(1 for x in sorted_window if x >= dnf_val)
    if dnf_count >= 2:
        return dnf_val
        
    # Trim first and last
    trimmed = sorted_window[1:4]
    
    # If any DNF remains in trimmed (shouldn't happen with dnf_count < 2), handle it
    # but theoretically trimmed[0] is >= second best, trimmed[2] is <= second worst.
    return round(sum(trimmed) / 3, 3)


def _wca_mo3(attempts: list[float]) -> float | None:
    """Mean of 3 (WCA): Simple average, DNF if any attempt is DNF."""
    if len(attempts) < 3:
        return None
    window = attempts[-3:]
    dnf_val = TimeConvert.DNF_VALUE
    
    if any(x >= dnf_val for x in window):
        return dnf_val
        
    return round(sum(window) / 3, 3)


def _best_rolling_avg(attempts: list[float], window_size: int, is_mo3: bool) -> float | None:
    """Find the best WCA average across the entire history."""
    if len(attempts) < window_size:
        return None
    
    best = None
    for i in range(len(attempts) - window_size + 1):
        window = attempts[i : i + window_size]
        if is_mo3:
            avg = _wca_mo3(window)
        else:
            avg = _wca_ao5(window)
            
        if avg is None: continue
        if best is None or avg < best:
            best = avg
    return best


def compute_display_stats(attempts: list[float], project: str) -> dict:
    """
    Stats for personal queries (ask).
    """
    res = {"pb": None, "cur_avg": None, "aoAll": None, "label": "ao5"}
    if not attempts:
        return res
        
    dnf_val = TimeConvert.DNF_VALUE
    valid_attempts = [x for x in attempts if x < dnf_val]
    
    res["pb"] = min(valid_attempts) if valid_attempts else dnf_val
    res["cur_avg"] = _wca_avg(attempts, project)
    res["label"] = "mo3" if project in MO3_PROJECTS else "ao5"
    
    if valid_attempts:
        res["aoAll"] = round(sum(valid_attempts) / len(valid_attempts), 3)
    else:
        res["aoAll"] = dnf_val
        
    return res


def compute_rank_stats(attempts: list[float], project: str) -> dict:
    """
    Stats for leaderboard queries (rank).
    """
    if not attempts:
        return {"pb": None, "best_avg": None, "aoAll": None}
        
    dnf_val = TimeConvert.DNF_VALUE
    valid_attempts = [x for x in attempts if x < dnf_val]
    
    window = 3 if project in MO3_PROJECTS else 5
    is_mo3 = project in MO3_PROJECTS
    
    return {
        "pb": min(valid_attempts) if valid_attempts else dnf_val,
        "best_avg": _best_rolling_avg(attempts, window, is_mo3),
        "aoAll": round(sum(valid_attempts) / len(valid_attempts), 3) if valid_attempts else dnf_val,
    }


# --------------------------------------------------------------------------- #
#  Member                                                                      #
# --------------------------------------------------------------------------- #

class Member:
    """
    Lightweight facade over the storage layer using student_id as anchor.
    """

    @staticmethod
    def create(name: str, student_id: str, extra_id: str = None, qid: str = None) -> None:
        db.upsert_member(student_id, name, qid, extra_id)

    @staticmethod
    def update_extra(student_id: str, extra_id: str) -> None:
        db.update_member_extra(student_id, extra_id)

    @staticmethod
    def bind(qid: str, name: str, student_id: str = None) -> str:
        """
        Bind a QID to a member. 
        If an account has a placeholder SID (TEMP_), a real SID must be provided.
        """
        members = db.get_members_by_name(name)
        if not members:
            return f"未找到名为 {name} 的用户。"

        target = None
        if student_id:
            # 优先寻找匹配提供的学号的成员
            target = next((m for m in members if m['student_id'] == student_id), None)
            
            # 如果没找到，但只有一个同名成员且它是 TEMP_，则认为用户是要给这个 TEMP_ 账号赋予新 SID
            if not target and len(members) == 1 and members[0]['student_id'].startswith("TEMP_"):
                target = members[0]
                # 这种情况我们需要执行 SID 更新逻辑
                if db.bind_qid(qid, target['student_id'], student_id):
                    return f"迁移并绑定成功！已将您的数据从临时账号迁移到学号 {student_id}。"
                else:
                    return f"绑定失败：学号 {student_id} 可能已被占用，或您的 QQ 已绑定其他账号。"
            
            if not target:
                return f"未找到学号为 {student_id} 的用户 {name}。"
        else:
            if len(members) > 1:
                ids = [m['student_id'] for m in members]
                return f"发现多个名为 {name} 的用户，请输入学号以唯一确定：\n" + "\n".join(ids)
            
            target = members[0]
            if target['student_id'].startswith("TEMP_"):
                return f"用户 {name} 尚未设置正式学号。请使用：/bind {name} <您的真实学号> 以完成绑定并迁移旧数据。"

        # 正常绑定逻辑
        if db.bind_qid(qid, target['student_id']):
            return f"绑定成功！已关联到用户 {name} ({target['student_id']})。"
        else:
            return "绑定失败：该 QQ 已绑定到其他账号。"


    @staticmethod
    def unbind(name: str, student_id: str = None) -> str:
        members = db.get_members_by_name(name)
        if not members:
            return f"未找到名为 {name} 的用户。"
            
        if student_id:
            target = next((m for m in members if m['student_id'] == student_id), None)
            if not target: return f"未找到 ID 为 {student_id} 的用户 {name}。"
        else:
            if len(members) > 1:
                ids = [m['student_id'] for m in members]
                return f"发现多个名为 {name} 的用户，请提供学号以解绑：\n" + "\n".join(ids)
            target = members[0]
            
        db.unbind_qid(target['student_id'])
        return f"用户 {name} ({target['student_id']}) 已解绑。"

    @staticmethod
    def delete(student_id: str) -> bool:
        if not db.member_exists(student_id):
            return False
        db.delete_member(student_id)
        return True

    @staticmethod
    def exists(student_id: str) -> bool:
        return db.member_exists(student_id)

    @staticmethod
    def get_sid_by_qid(qid: str) -> str | None:
        return db.get_sid_by_qid(qid)

    @staticmethod
    def get_name_by_sid(student_id: str) -> str:
        row = db.get_member_by_sid(student_id)
        return row['name'] if row else "未知"

    @staticmethod
    def get_members_by_name(name: str) -> list[dict]:
        return db.get_members_by_name(name)

    # ---- Scores ----------------------------------------------------------- #

    @staticmethod
    def upload_score(student_id: str, scope: str, project: str, score_text: str) -> dict:
        """
        Record scores and return stats for feedback.
        """
        # Stats before
        old_attempts = db.get_attempts(student_id, scope, project)
        old_stats = compute_display_stats(old_attempts, project)
        
        # Insert
        tokens = [t for t in score_text.split() if t]
        import datetime
        ts = datetime.datetime.now().isoformat()
        
        new_scores = []
        for token in tokens:
            try:
                seconds = TimeConvert.time_to_seconds(token)
                db.insert_attempt(student_id, scope, project, seconds, ts)
                new_scores.append(seconds)
            except ValueError:
                continue
        
        if not new_scores:
            return {"success": False}
            
        # Stats after
        new_attempts = db.get_attempts(student_id, scope, project)
        new_stats = compute_display_stats(new_attempts, project)
        
        return {
            "success": True,
            "project": project,
            "new_scores": new_scores,
            "old_stats": old_stats,
            "new_stats": new_stats
        }

    @staticmethod
    def undo_last_score(student_id: str, scope: str) -> str:
        deleted = db.delete_last_batch(student_id, scope)
        if not deleted:
            return "暂无可撤销的成绩。"
        
        summary = ", ".join([f"{d['project']}: {TimeConvert.seconds_to_time(d['seconds'])}" for d in deleted])
        return f"已成功撤销以下成绩：\n{summary}"

    @staticmethod
    def ask_score(student_id: str, scope: str, project: str) -> str:
        attempts = db.get_attempts(student_id, scope, project)
        stats = compute_display_stats(attempts, project)
        tc = TimeConvert.seconds_to_time
        return (
            f"pb {tc(stats['pb'])}\n"
            f"{stats['label']}(当前) {tc(stats['cur_avg'])}\n"
            f"aoAll {tc(stats['aoAll'])}"
        )

    @staticmethod
    def ask_all_scores(student_id: str, scope: str) -> str:
        from .constants import ALL_PROJECT_TYPES
        lines = []
        for project in ALL_PROJECT_TYPES:
            attempts = db.get_attempts(student_id, scope, project)
            if attempts:
                stats = compute_display_stats(attempts, project)
                tc = TimeConvert.seconds_to_time
                lines.append(
                    f"{project}: pb {tc(stats['pb'])}  {stats['label']} {tc(stats['cur_avg'])}"
                )
        return "\n".join(lines) if lines else "暂无成绩"


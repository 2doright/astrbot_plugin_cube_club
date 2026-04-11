from pathlib import Path
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .constants import ALL_PROJECT_TYPES, OTHER_TYPES
from .models import Member
from .rank import RankQuery
from . import db
from .time_utils import TimeConvert

from datetime import datetime, date, timedelta
import calendar
import re
import os
from .render import get_renderer

@register("cube_club", "CubeClub", "打乱成绩记录与排行插件", "1.1.1")
class CubeClubPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 初始化数据库
        plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name
        db_path = plugin_data_path / "cube_club.db"
        db.init_db(db_path)
        logger.info(f"CubeClub Plugin for AstrBot initialized. Database at {db_path}")

    @filter.command("reg", alias={"注册"})
    async def reg(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            qid = event.get_sender_id()
            
            # 格式: /reg <Name> <SID> [Extra]
            if len(args) < 2:
                yield event.plain_result("格式错误。格式: /reg <姓名> <学号> [附加信息]")
                return
            
            name = args[0]
            sid = args[1]
            extra = " ".join(args[2:]) if len(args) > 2 else None
            
            # 检查学号冲突
            if db.member_exists(sid):
                yield event.plain_result(f"学号 {sid} 已被注册。如有疑问请联系管理员。")
                return
            
            # 检查当前 QID 是否已绑定
            if Member.get_sid_by_qid(qid):
                yield event.plain_result(f"您的 QQ 已经绑定了一个账号。如需更换，请先解绑或联系管理员。")
                return

            Member.create(name, sid, extra, qid)
            yield event.plain_result(f"注册成功！\n姓名：{name}\n学号：{sid}\nID：{extra or '无'}")
        except Exception as e:
            logger.error(f"reg error: {e}")
            yield event.plain_result("注册失败，请检查输入格式。")

    @filter.command("bind", alias={"绑定"})
    async def bind(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if not args:
                yield event.plain_result("格式: /bind <姓名> [学号]")
                return
            
            qid = event.get_sender_id()
            name = args[0]
            sid = args[1] if len(args) > 1 else None
            
            result = Member.bind(qid, name, sid)
            yield event.plain_result(result)
        except Exception as e:
            logger.error(f"bind error: {e}")
            yield event.plain_result("绑定失败。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("unbind", alias={"解绑"})
    async def unbind(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if not args:
                yield event.plain_result("格式: /unbind <姓名> [学号]")
                return
            
            name = args[0]
            sid = args[1] if len(args) > 1 else None
            
            result = Member.unbind(name, sid)
            yield event.plain_result(result)
        except Exception as e:
            logger.error(f"unbind error: {e}")
            yield event.plain_result("解绑失败。")

    @filter.command("update", alias={"改ID"})
    async def update_profile(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            qid = event.get_sender_id()
            sid = Member.get_sid_by_qid(qid)
            
            if not sid:
                yield event.plain_result("您尚未绑定用户。")
                return
            
            if not args:
                yield event.plain_result("格式: /update <新附加ID>")
                return
            
            new_extra = " ".join(args)
            Member.update_extra(sid, new_extra)
            yield event.plain_result(f"附加ID已更新为: {new_extra}")
        except Exception as e:
            logger.error(f"update error: {e}")
            yield event.plain_result("更新失败。")

    @filter.command("me", alias={"我"})
    async def me(self, event: AstrMessageEvent):
        qid = event.get_sender_id()
        sid = Member.get_sid_by_qid(qid)
        if sid:
            member = db.get_member_by_sid(sid)
            yield event.plain_result(f"当前绑定：\n姓名：{member['name']}\nID：{member['extra_id'] or '无'}")
        else:
            yield event.plain_result("当前 QQ 尚未绑定用户。")

    @filter.command("undo", alias={"撤销"})
    async def undo(self, event: AstrMessageEvent):
        qid = event.get_sender_id()
        sid = Member.get_sid_by_qid(qid)
        if not sid:
            yield event.plain_result("您尚未绑定用户。")
            return
        
        result = Member.undo_last_score(sid, "daily")
        yield event.plain_result(result)

    @filter.command("map", alias={"热力图"})
    async def map_heatmap(self, event: AstrMessageEvent):
        try:
            year, group = self._parse_map_parameters(event.message_str)
            if not group:
                qid = event.get_sender_id()
                sid = Member.get_sid_by_qid(qid)
                if not sid:
                    yield event.plain_result("您尚未绑定用户。")
                    return
            else:
                sid = None

            if year is None:
                current = datetime.now()
                year = current.year
                month = current.month
            else:
                month = None

            counts = db.get_daily_attempt_counts(sid, year, month)
            if not counts:
                period_text = f"{year}年" if month is None else f"{year}年{month}月"
                if group:
                    yield event.plain_result(f"社团{period_text}暂无成绩记录。")
                else:
                    yield event.plain_result(f"{period_text}暂无个人成绩记录。")
                return

            data = self._build_heatmap_data(counts, year, month, group)
            renderer = get_renderer()
            png_bytes = renderer.render_heatmap(data)

            plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name
            if not plugin_data_path.exists():
                plugin_data_path.mkdir(parents=True, exist_ok=True)

            image_path = plugin_data_path / "temp_map.png"
            image_path.write_bytes(png_bytes)
            yield event.image_result(str(image_path.absolute()))
        except Exception as e:
            logger.error(f"map_heatmap error: {e}")
            if 'counts' in locals() and counts:
                lines = [f"{day}: {count} 次" for day, count in sorted(counts.items())]
                yield event.plain_result("热力图生成失败，已返回文本结果：\n" + "\n".join(lines))
            else:
                yield event.plain_result("热力图查询失败。")

    def _format_trend(self, old_val, new_val):
        """Format trend with arrows."""
        dnf = TimeConvert.DNF_VALUE
        if new_val is None: return ""
        
        tc = TimeConvert.seconds_to_time
        if old_val is None or old_val >= dnf:
            # First recording
            return f"{tc(new_val)}"
            
        diff = new_val - old_val
        if abs(diff) < 0.0001:
            return f"{tc(new_val)} (-)"
            
        arrow = "↓" if diff < 0 else "↑"
        # 简单使用 emoji，某些环境可能支持 ANSI 颜色，但这里保持通用
        return f"{tc(new_val)} ({arrow}{abs(diff):.2f})"

    def _parse_map_parameters(self, message: str) -> tuple[int | None, bool]:
        """Parse `/map` or `/热力图` arguments for optional year and group mode."""
        args = message.split()[1:]
        year = None
        group = False
        for token in args:
            lower = token.lower()
            if lower == "group":
                group = True
                continue

            if re.fullmatch(r"\d{2}", token):
                year = 2000 + int(token)
            elif re.fullmatch(r"\d{4}", token):
                year = int(token)
        return year, group

    def _build_heatmap_data(self, counts: dict[str, int], year: int, month: int | None, group: bool) -> dict:
        """Prepare heatmap rendering data for monthly or yearly view."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chart_type = "year" if month is None else "month"
        label = "社团活跃度" if group else "个人活跃度"
        period_label = f"{year}年" if month is None else f"{year}年{month}月"
        title = f"{label} 热力图"
        subtitle = period_label

        if chart_type == "month":
            start_day = date(year, month, 1)
            week_start = start_day - timedelta(days=(start_day.weekday() + 1) % 7)
            next_month = date(year + (month // 12), (month % 12) + 1, 1)
            final_day = next_month - timedelta(days=1)
            end_day = final_day + timedelta(days=(6 - ((final_day.weekday() + 1) % 7)))
        else:
            start_day = date(year, 1, 1)
            week_start = start_day - timedelta(days=(start_day.weekday() + 1) % 7)
            end_day = date(year, 12, 31)
            end_day = end_day + timedelta(days=(6 - ((end_day.weekday() + 1) % 7)))

        total_weeks = ((end_day - week_start).days // 7) + 1
        cell_size = 12
        gap = 4
        x_spacing = cell_size + gap
        y_spacing = cell_size + gap
        max_count = max(counts.values()) if counts else 0

        def bucket_level(value: int) -> int:
            if value <= 0:
                return 0
            if max_count <= 4:
                return min(value, 4)
            if value <= max_count * 0.25:
                return 1
            if value <= max_count * 0.5:
                return 2
            if value <= max_count * 0.75:
                return 3
            return 4

        color_map = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
        cells = []
        day = week_start
        while day <= end_day:
            week_index = (day - week_start).days // 7
            dow = (day.weekday() + 1) % 7
            count = counts.get(day.isoformat(), 0)
            level = bucket_level(count)
            opacity = 1.0 if chart_type == "year" or day.month == month else 0.3
            cells.append({
                "x": 40 + week_index * x_spacing,
                "y": 80 + dow * y_spacing,
                "fill": color_map[level],
                "opacity": opacity,
                "tooltip": f"{day.isoformat()}：{count} 次",
                "date": day.isoformat(),
                "count": count,
                "current_period": chart_type == "year" or day.month == month,
            })
            day += timedelta(days=1)

        month_labels = []
        if chart_type == "year":
            for month_index in range(1, 13):
                month_first = date(year, month_index, 1)
                week_index = (month_first - week_start).days // 7
                month_labels.append({
                    "x": 40 + week_index * x_spacing,
                    "label": month_first.strftime("%b")
                })

        legend = [
            {"color": "#ebedf0", "text": "0"},
            {"color": "#9be9a8", "text": "1+"},
            {"color": "#40c463", "text": "2+"},
            {"color": "#30a14e", "text": "3+"},
            {"color": "#216e39", "text": "4+"},
        ]

        width = 40 + total_weeks * x_spacing + 40
        height = 120 + 7 * y_spacing + 80

        return {
            "title": title,
            "subtitle": subtitle,
            "now": now,
            "cells": cells,
            "month_labels": month_labels,
            "legend": legend,
            "width": width,
            "height": height,
        }

    @filter.command(ALL_PROJECT_TYPES[0], alias=set(ALL_PROJECT_TYPES[1:]))
    async def record(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            command_word = event.message_str.split()[0]
            project = command_word
            
            qid = event.get_sender_id()
            sid = Member.get_sid_by_qid(qid)
            if not sid:
                yield event.plain_result("当前 QQ 尚未绑定用户。")
                return
            
            if not args:
                yield event.plain_result("未输入成绩。")
                return
            
            res = Member.upload_score(sid, "daily", project, " ".join(args))
            if not res["success"]:
                yield event.plain_result("成绩记录失败（可能是格式错误）。")
                return
            
            # 详细反馈
            os = res["old_stats"]
            ns = res["new_stats"]
            scores_str = ", ".join([TimeConvert.seconds_to_time(s) for s in res["new_scores"]])
            
            msg = f"记录成功！项目：{project}\n成绩：{scores_str}"
            
            # PB status
            if ns["pb"] is not None:
                if os["pb"] is None or ns["pb"] < os["pb"]:
                    msg += " (PB! 👑)"
            
            # Trend
            label = ns["label"]
            trend = self._format_trend(os["cur_avg"], ns["cur_avg"])
            msg += f"\n当前{label}: {trend}"
            
            yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"record error: {e}")
            yield event.plain_result("数据格式有误。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.regex(r"^(comp|比赛)(\d{2})?(?!\d)(?:\s|$)")
    async def comp(self, event: AstrMessageEvent):
        try:
            match = re.match(r"^(comp|比赛)(\d{2})?(?!\d)", event.message_str)
            year = match.group(2) or datetime.now().strftime("%y")
            scope = f"comp{year}"
            
            args = event.message_str.split()[1:]
            if len(args) < 3:
                yield event.plain_result(f"竞赛记录模式 ({scope})\n格式: /比赛[年份] <项目> <姓名/学号> <成绩>")
                return

            project = args[0]
            query = args[1]
            score_text = " ".join(args[2:])
            
            if project not in ALL_PROJECT_TYPES:
                yield event.plain_result(f"未知项目: {project}")
                return

            # 解析用户
            sid = None
            member = db.get_member_by_sid(query)
            if member: 
                sid = query
            else:
                members = db.get_members_by_name(query)
                if len(members) == 1:
                    sid = members[0]['student_id']
                elif len(members) > 1:
                    yield event.plain_result(f"存在多个名为 {query} 的用户，请使用学号。")
                    return
                else:
                    yield event.plain_result(f"未找到用户 {query}。")
                    return
            
            res = Member.upload_score(sid, scope, project, score_text)
            name = Member.get_name_by_sid(sid)
            yield event.plain_result(f"[{scope}] {name} {project} 成绩记录成功")
        except Exception as e:
            logger.error(f"comp error: {e}")
            yield event.plain_result("竞赛成绩记录失败。")

    @filter.command("ask", alias={"查"})
    async def ask(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if not args:
                yield event.plain_result("格式: /ask <项目/num/all>")
                return
                
            project_type = args[0].strip()
            qid = event.get_sender_id()
            sid = Member.get_sid_by_qid(qid)
            if not sid:
                yield event.plain_result("当前 QQ 尚未绑定用户。")
                return

            if project_type == "num":
                data = db.get_project_count_by_scope("daily").get(sid, 0)
                yield event.plain_result(f"已参与项目数: {data}")
            elif project_type == "all":
                yield event.plain_result(Member.ask_all_scores(sid, "daily"))
            else:
                if project_type not in ALL_PROJECT_TYPES and project_type not in OTHER_TYPES:
                    yield event.plain_result("未知项目类型。")
                    return
                yield event.plain_result(Member.ask_score(sid, "daily", project_type))
        except Exception as e:
            logger.error(f"ask error: {e}")
            yield event.plain_result("查询失败。")

    @filter.command("askwho", alias={"查他"})
    async def askwho(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if len(args) < 1:
                yield event.plain_result("格式: /askwho <姓名> [项目]")
                return

            query = args[0] # Only name
            project_type = args[1] if len(args) > 1 else "all"
            
            members = db.get_members_by_name(query)
            if not members:
                yield event.plain_result("未找到该用户。")
                return

            msg_blocks = []
            multi = len(members) > 1
            for m in members:
                sid = m['student_id']
                if project_type == "all":
                    data = Member.ask_all_scores(sid, "daily")
                elif project_type == "num":
                    cnt = db.get_project_count_by_scope("daily").get(sid, 0)
                    data = f"已参与项目数: {cnt}"
                else:
                    data = Member.ask_score(sid, "daily", project_type)
                
                name_display = f"{m['name']}[*{sid[-4:]}]" if multi else m['name']
                msg_blocks.append(f"【{name_display}】\n{data}")

            yield event.plain_result("\n\n".join(msg_blocks))
        except Exception as e:
            logger.error(f"askwho error: {e}")
            yield event.plain_result("查询失败。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("del", alias={"删"})
    async def del_member(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if not args:
                yield event.plain_result("格式: /del <姓名/学号>")
                return
            
            query = args[0]
            sid = None
            member = db.get_member_by_sid(query)
            if member:
                sid = query
            else:
                members = db.get_members_by_name(query)
                if len(members) == 1:
                    sid = members[0]['student_id']
                elif len(members) > 1:
                    yield event.plain_result("存在多个同名用户，请提供学号以删除。")
                    return

            if sid and Member.delete(sid):
                yield event.plain_result(f"用户 {query} 删除成功。")
            else:
                yield event.plain_result("删除失败或用户不存在。")
        except Exception as e:
            logger.error(f"del_member error: {e}")
            yield event.plain_result("删除失败。")

    @filter.regex(r"^(?:(rk)(\d{2})|(rkd|rkm|rky|rka|rkc|日榜|月榜|年榜|总榜|全能榜))(?:\s|$)")
    async def rk(self, event: AstrMessageEvent):
        try:
            match = re.match(r"^(?:(rk)(\d{2})|(rkd|rkm|rky|rka|rkc|日榜|月榜|年榜|总榜|全能榜))(?:\s|$)", event.message_str)
            cmd = match.group(3) if match.group(3) else match.group(1)
            year = match.group(2) if match.group(3) is None else None
            args = event.message_str.split()[1:]

            _cmd_map = {
                "rkd": ("daily", "day"), "日榜": ("daily", "day"),
                "rkm": ("daily", "month"), "月榜": ("daily", "month"),
                "rky": ("daily", "year"), "年榜": ("daily", "year"),
                "rka": ("daily", "alltime"), "总榜": ("daily", "alltime"),
                "rkc": ("all", "count"), "全能榜": ("all", "count"),
            }
            
            scope, rk_type = "daily", "alltime"
            if cmd in _cmd_map:
                scope, rk_type = _cmd_map[cmd]
            elif year:
                scope = f"comp{year}"
            
            if rk_type == "count":
                try:
                    data = RankQuery.get_rank_data(scope, "count")
                    if data["results"]:
                        renderer = get_renderer()
                        png_bytes = renderer.render_rank(data)
                        
                        # Save to a temporary file
                        plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name
                        if not plugin_data_path.exists():
                            plugin_data_path.mkdir(parents=True, exist_ok=True)
                        
                        image_path = plugin_data_path / "temp_rank.png"
                        image_path.write_bytes(png_bytes)
                        
                        yield event.image_result(str(image_path.absolute()))
                        return
                except Exception as e:
                    logger.warning(f"Image generation failed: {e}. Falling back to text.")

                yield event.plain_result(RankQuery.get_rank_list(scope, "count"))
                return

            if len(args) != 2:
                yield event.plain_result("格式: /rkX <项目> <pb|ao5|mo3|aoAll>")
                return

            proj, stat = args[0], args[1]
            if stat in ("ao5", "mo3"): stat = "ao5/mo3"
            
            # --- Image Generation ---
            try:
                data = RankQuery.get_rank_data(scope, rk_type, proj, stat)
                if data["results"]:
                    renderer = get_renderer()
                    png_bytes = renderer.render_rank(data)
                    
                    # Save to a temporary file
                    plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name
                    if not plugin_data_path.exists():
                        plugin_data_path.mkdir(parents=True, exist_ok=True)
                    
                    image_path = plugin_data_path / "temp_rank.png"
                    image_path.write_bytes(png_bytes)
                    
                    yield event.image_result(str(image_path.absolute()))
                    return
            except Exception as e:
                logger.warning(f"Image generation failed: {e}. Falling back to text.")
            
            # Fallback to text
            yield event.plain_result(RankQuery.get_rank_list(scope, rk_type, proj, stat))
        except Exception as e:
            logger.error(f"rk error: {e}")
            yield event.plain_result("榜单查询失败。")

    @filter.command("help", alias={"帮助"})
    async def help_cmd(self, event: AstrMessageEvent):
        args = event.message_str.split()[1:]
        
        # 定义分级帮助内容
        categories = {
            "1": {
                "title": "👤 账号管理",
                "content": (
                    "- `/reg <姓名> <学号> [ID]`\n"
                    "  别名: `/注册`。在 CubeClub 档案库中创建您的身份。\n"
                    "  学号是您的唯一标识；[ID]可选，将替换你的名字显示。\n\n"
                    "- `/bind <姓名> [学号]`\n"
                    "  别名: `/绑定`。将您的当前 QQ 账号关联到已有档案。\n\n"
                    "- `/update <新ID>`\n"
                    "  别名: `/改ID`。随时更新档案中的[ID]。\n\n"
                    "- `/me`\n"
                    "  别名: `/我`。即时查看当前绑定的账号详细资料。"
                )
            },
            "2": {
                "title": "⏱️ 成绩记录",
                "content": (
                    "- `/<项目代码> <成绩1> [成绩2 ...]`\n"
                    "  直接输入项目缩写进行录入。支持一次性录入多个成绩。\n"
                    "  示例: `/333 12.34 10.50 DNF` (空格分隔)\n\n"
                    "- **成绩格式说明**:\n"
                    "  - 秒数: `12.34`\n"
                    "  - 分秒: `1:02.50` (会自动换算为 62.50s)\n"
                    "  - 特殊: `DNF` (未完赛成绩)\n\n"
                    "- **支持项目**: 222-777, 333oh, 333bf, pyram, sq1, skewb, minx, clock, hrd, nhrd 等。\n\n"
                    "- `/undo`\n"
                    "  别名: `/撤销`。录入失误？移除上一条日常记录成绩。"
                )
            },
            "3": {
                "title": "🔍 成绩查询",
                "content": (
                    "- `/ask <项目 | all | num>`\n"
                    "  别名: `/查`。回顾个人奋斗历程。\n"
                    "  - **项目代码**: 如 `/ask 333`，查看该项目 PB 与近期统计。\n"
                    "  - **all**: 摘要式列出您所有参与项目的成绩。\n"
                    "  - **num**: 快速查看您已累计参与的项目总数。\n\n"
                    "- `/askwho <姓名> [项目]`\n"
                    "  别名: `/查他`。通过姓名搜索他人的公开成绩。\n"
                    "  若遇同名用户，系统将显示学号后四位以示区别。"
                )
            },
            "4": {
                "title": "🏆 排行榜",
                "content": (
                    "- `/rk[d|m|y|a] <项目> <统计类型>`\n"
                    "  多维度实力角逐。别名: `/日榜`, `/月榜`, `/年榜`, `/总榜`。\n"
                    "  - **rkd (Day)**: 今日产生的最新记录排行。\n"
                    "  - **rka (All)**: 历史全时期最佳战绩大榜。\n\n"
                    "- `/rkc`\n"
                    "  别名: `/全能榜`。按用户涉及的项目广度进行排名。\n\n"
                    "- **统计类型关键词**:\n"
                    "  - `pb` (单次最高纪录)\n"
                    "  - `ao5` (传统五次平均, 剔除极值)\n"
                    "  - `mo3` (连续三次均值, 适用于 666/777/盲拧等)"
                )
            },
            "5": {
                "title": "📊 热力图",
                "content": (
                    "- `/map [年份] [group]`\n"
                    "  别名: `/热力图`。显示个人或社团的 GitHub 风格活跃热力图。\n"
                    "  - 不带参数: 当前月个人热力图。\n"
                    "  - `/map 24`: 显示 2024 年全年热力图。\n"
                    "  - `/map group`: 显示当前月社团活跃热力图。\n"
                    "  - `/map 24 group`: 显示 2024 年社团活跃热力图。"
                )
            },
            "6": {
                "title": "🛠️ 管理员指令",
                "content": (
                    "- `/unbind <姓名> [学号]`\n"
                    "  别名: `/解绑`。解除指定用户的 QQ 绑定关系。\n\n"
                    "- `/comp[年份] <项目> <姓名/学号> <成绩>`\n"
                    "  别名: `/比赛[年份]`。录入线下正式赛记录（独立榜单）。\n"
                    "  示例: `/比赛24 333 张三 9.80`\n\n"
                    "- `/del <姓名/学号>`\n"
                    "  别名: `/删`。**警告**：永久抹除该用户及其所有历史成绩！"
                )
            }
        }

        if args and args[0] in categories:
            cat = categories[args[0]]
            msg = (
                f"### 🧩 CubeClub 帮助 | {cat['title']}\n"
                f"---\n\n"
                f"{cat['content']}"
            )
        else:
            msg = (
                "## 🧩 CubeClub 指令帮助 (v1.1)\n"
                "---\n"
                "1. **👤 账号管理** (注册、绑定、资料)\n"
                "2. **⏱️ 成绩记录** (录入、项目、撤销)\n"
                "3. **🔍 成绩查询** (查记录、查他人)\n"
                "4. **🏆 排行榜** (日/月/年/总/全能)\n"
                "5. **📊 热力图** (个人、社团活跃度)\n"
                "6. **🛠️ 管理员指令** (解绑、线下赛录入)\n"
                "---\n"
                "输入 `/help <序号>` 查看详情 (示例: `/help 1`)\n"
            )

        yield event.plain_result(msg)


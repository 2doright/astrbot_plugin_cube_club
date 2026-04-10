from pathlib import Path
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .constants import ALL_PROJECT_TYPES, OTHER_TYPES
from .models import Member
from .rank import RankQuery
from . import db

from datetime import datetime
import re

@register("cube_club", "CubeClub", "打乱成绩记录与排行插件", "1.0.0")
class CubeClubPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 初始化数据库（如果不存在则创建表和索引）
        # 遵循 AstrBot 存储规范：data/plugin_data/{plugin_name}/
        plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name
        db_path = plugin_data_path / "cube_club.db"
        db.init_db(db_path)
        logger.info(f"CubeClub Plugin for AstrBot initialized. Database bounded at {db_path}")

    @filter.command("reg", alias={"注册"})
    async def reg(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            qid = event.get_sender_id()
            flag = Member.exists(qid)
            
            if flag:
                yield event.plain_result(f"该QQ已存在用户,用户名为:{Member.get_name_by_qid(qid)}\n如有需要,请联系管理员删除当前用户")
                return

            sign_text = " ".join(args).strip()
            if sign_text:
                parts = sign_text.split(" ", 1)
                if len(parts) >= 2:
                    name, extra_id = parts[0], parts[1]
                    Member.create(name, qid, extra_id)
                    yield event.plain_result(f"{name}登记成功, ID:{extra_id}")
                else:
                    name = sign_text
                    Member.create(name, qid)
                    yield event.plain_result(f"{name}登记成功")
            else:
                yield event.plain_result("缺失必要信息(Name)")
        except Exception as e:
            logger.error(f"reg error: {e}")
            yield event.plain_result("格式输入有误,指令格式: /help reg以查看输入格式")

    @filter.command("me", alias={"我"})
    async def me(self, event: AstrMessageEvent):
        args = event.message_str.split()[1:]
        if args:
            yield event.plain_result("存在多余参数")
            return
        qid = event.get_sender_id()
        if Member.exists(qid):
            yield event.plain_result(f"当前QQ绑定用户名为:{Member.get_name_by_qid(qid)}")
        else:
            yield event.plain_result("当前QQ尚未绑定用户")

    @filter.command("who", alias={"查人"})
    async def who(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if not args:
                yield event.plain_result("参数不足,格式: /who name/qid")
                return
            information = args[0]
            if information.isdigit():
                qid = information
                name = Member.get_name_by_qid(qid)
                if name == "未绑定":
                    yield event.plain_result("该QQ未绑定用户")
                else:
                    yield event.plain_result(f"该QQ绑定用户为:{name}")
            else:
                name = information
                qid = Member.get_qid_by_name(name)
                if qid != "未绑定":
                    yield event.plain_result(f"当前用户绑定QQ为:{qid}")
                else:
                    yield event.plain_result("当前用户不存在")
        except Exception as e:
            logger.error(f"who error: {e}")
            yield event.plain_result("格式输入有误,指令格式: /help who以查看输入格式")
            
    # 仅使用项目类型（如 /333）作为指令进行日常记录
    @filter.command(ALL_PROJECT_TYPES[0], alias=set(ALL_PROJECT_TYPES[1:]))
    async def record(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            command_word = event.message_str.split()[0]
            
            project = command_word
            new_score_text = " ".join(args)

            qid = event.get_sender_id()
            if not Member.exists(qid):
                yield event.plain_result("当前QQ尚未绑定用户")
                return
                
            if new_score_text:
                Member.upload_score(qid, "daily", project, new_score_text)
                yield event.plain_result(f"[日常] {project} 成绩记录成功")
            else:
                yield event.plain_result("未输入成绩,记录失败")
        except Exception as e:
            logger.error(f"record error: {e}")
            yield event.plain_result("数据格式有误,输入指令 /help record以查看输入格式")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.regex(r"^(comp|比赛)(\d{2})?(?!\d)(?:\s|$)")
    async def record2(self, event: AstrMessageEvent):
        try:
            # 使用正则匹配获取年份
            match = re.match(r"^(comp|比赛)(\d{2})?(?!\d)", event.message_str)
            if match:
                year = match.group(2)
            else:
                year = None
                
            if not year:
                year = datetime.now().strftime("%y")

            scope = f"comp{year}"
            args = event.message_str.split()[1:]
            
            if not args:
                yield event.plain_result(f"竞赛记录模式 ({scope})\n格式: /比赛[年份] <项目> <姓名> <成绩>\n示例: /比赛 333 张三 10.5")
                return

            if len(args) < 3:
                yield event.plain_result("参数不足。格式: /比赛[年份] <项目> <姓名> <成绩>")
                return

            project = args[0]
            name = args[1]
            score_text = " ".join(args[2:])
            
            if project not in ALL_PROJECT_TYPES:
                yield event.plain_result(f"未知项目: {project}")
                return

            qid = Member.get_qid_by_name(name)
            if qid == "未绑定":
                yield event.plain_result(f"用户 {name} 不存在")
                return
            
            Member.upload_score(qid, scope, project, score_text)
            yield event.plain_result(f"[{scope}] {name} {project} 成绩记录成功")
        except Exception as e:
            logger.error(f"record2 error: {e}")
            yield event.plain_result("数据格式有误")

    @filter.command("ask", alias={"查"})
    async def ask(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if not args:
                yield event.plain_result("输入有误,指令格式: /help ask以查看输入格式")
                return
            project_type = args[0].strip()
            if project_type not in ALL_PROJECT_TYPES and project_type not in OTHER_TYPES:
                yield event.plain_result("项目类型输入错误,指令格式: /help type以查看开设的项目")
                return

            qid = event.get_sender_id()
            if Member.get_name_by_qid(qid) == "未绑定":
                yield event.plain_result("当前QQ尚未绑定用户")
                return

            if project_type == "num":
                data = Member.count_projects(qid, "daily")
            elif project_type == "all":
                data = Member.ask_all_scores(qid, "daily")
            else:
                data = Member.ask_score(qid, "daily", project_type)
            yield event.plain_result(f"{data}")
        except Exception as e:
            logger.error(f"ask error: {e}")
            yield event.plain_result("输入有误,指令格式: /help ask以查看输入格式")

    @filter.command("askwho", alias={"查他"})
    async def askwho(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if len(args) < 2:
                yield event.plain_result("参数不足,格式: /askwho <name> <project>")
                return

            name, project_type = args[0], args[1]
            if project_type not in ALL_PROJECT_TYPES and project_type not in OTHER_TYPES:
                yield event.plain_result("项目类型输入错误,指令格式: /help type以查看开设的项目")
                return

            qid = Member.get_qid_by_name(name)
            if qid == "未绑定":
                yield event.plain_result("当前用户不存在")
                return

            if project_type == "num":
                data = Member.count_projects(qid, "daily")
            elif project_type == "all":
                data = Member.ask_all_scores(qid, "daily")
            else:
                data = Member.ask_score(qid, "daily", project_type)
            yield event.plain_result(f"{data}")
        except Exception as e:
            logger.error(f"askwho error: {e}")
            yield event.plain_result("输入有误,指令格式: /help askwho以查看输入格式")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("del", alias={"删"})
    async def del_member(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if not args:
                yield event.plain_result("未找到该用户")
                return
            name = args[0].strip()
            qid = Member.get_qid_by_name(name)
            if qid == "未绑定":
                yield event.plain_result("未找到该用户")
                return
            if Member.delete(qid):
                yield event.plain_result(f"用户{name}删除成功")
            else:
                yield event.plain_result(f"用户{name}删除失败")
        except Exception as e:
            logger.error(f"del_member error: {e}")
            yield event.plain_result("输入有误,指令格式: /help del以查看输入格式")

    @filter.regex(r"^(rk|榜|rkd|rkm|rky|rka|rkc|日榜|月榜|年榜|总榜|勤奋榜)(\d{2})?(?!\d)(?:\s|$)")
    async def rk(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            # 使用正则提取指令和年份
            match = re.match(r"^(rk|榜|rkd|rkm|rky|rka|rkc|日榜|月榜|年榜|总榜|勤奋榜)(\d{2})?(?!\d)", event.message_str)
            if not match:
                return # 不应该发生，既然触发了正则
            
            command_word = match.group(1)
            year = match.group(2)
            
            if command_word in ("rk", "榜"):
                # 如果只有 rk/榜，但没有年份，报错 (除非有子逻辑，但这里 rkYY 处理在下方)
                if not year:
                    yield event.plain_result("缺少参数,请输入指令: /help rk以查看输入格式")
                    return

            _cmd_map = {
                "rkd":  ("daily", "day"),      "日榜": ("daily", "day"),
                "rkm":  ("daily", "month"),    "月榜": ("daily", "month"),
                "rky":  ("daily", "year"),     "年榜": ("daily", "year"),
                "rka":  ("daily", "alltime"),  "总榜": ("daily", "alltime"),
                "rkc":  ("daily", "count"),    "勤奋榜": ("daily", "count"),
            }
            
            # 动态识别 rkYY
            scope = "daily"
            rank_type = None
            
            if command_word in _cmd_map:
                scope, rank_type = _cmd_map[command_word]
            elif command_word in ("rk", "榜") and year:
                # 识别到 rkYY 或 榜YY
                scope = f"comp{year}"
                rank_type = "alltime"
            elif command_word in ("rk", "榜"):
                # 默认使用当前年份竞赛 (如果有特殊逻辑处理无年份的rk)
                year = datetime.now().strftime("%y")
                scope = f"comp{year}"
                rank_type = "alltime"

            if not rank_type:
                yield event.plain_result("参数错误,请输入指令: /help rk以查看输入格式")
                return

            if rank_type == "count":
                rank_list = RankQuery.get_rank_list(scope, "count")
                yield event.plain_result(f"{rank_list}")
                return

            if len(args) != 2:
                yield event.plain_result("参数有误,格式: /rkXXX <project> <pb|ao5|mo3|aoAll>")
                return

            proj, stat = args[0], args[1]
            if proj not in ALL_PROJECT_TYPES or stat not in ("pb", "ao5", "mo3", "aoAll"):
                yield event.plain_result("参数有误,请输入指令: /help rk以查看输入格式")
                return

            if stat in ("ao5", "mo3"):
                stat = "ao5/mo3"

            rank_list = RankQuery.get_rank_list(scope, rank_type, proj, stat)
            yield event.plain_result(f"{rank_list}")
        except Exception as e:
            logger.error(f"rk error: {e}")
            yield event.plain_result(f"输入有误,输入/help rk以查看输入格式")

    @filter.command("help", alias={"帮助"})
    async def help_cmd(self, event: AstrMessageEvent):
        try:
            args = event.message_str.split()[1:]
            if not args:
                yield event.plain_result(
                    "当前可调用的指令有:(/help + 指令可查看具体信息)\n"
                    "help 帮助 | type 项目 | rktype 榜单类型\n"
                    "reg 注册 | me 我 | who 查人\n"
                    "<project> 成绩记录 | comp 赛事成绩记录(仅管理员)\n"
                    "ask 查 | askwho 查他/她 | rk 榜\n"
                    "del 删"
                )
                return
                
            command_word = args[0].strip()
            if command_word == "type":
                yield event.plain_result("目前开设的项目有: " + ", ".join(ALL_PROJECT_TYPES))
            elif command_word == "rktype":
                yield event.plain_result(
                    "目前支持的排行榜类型有:\n"
                    "rkd(日) rkm(月) rky(年) rka(总) rkc(勤奋)\n"
                    "赛事: rkYY(如rk24, rk26)"
                )
            elif command_word == "reg":
                yield event.plain_result("reg (注册) - 注册用户\n格式: /reg Name ID\nName: 用户名\nID: 用户ID")
            elif command_word == "me":
                yield event.plain_result("me (我) - 查询当前用户\n格式: /me")
            elif command_word == "who":
                yield event.plain_result("who (查人) - 查询他人信息\n格式: /who name/qid")
            elif command_word in ALL_PROJECT_TYPES:
                yield event.plain_result(
                    "project (成绩记录) - 记录日常成绩\n"
                    "格式: /<项目> <成绩>\n"
                    "示例: /333 10.5\n"
                    "支持项目: /help type 查看"
                )
            elif command_word in ("comp", "比赛"):
                yield event.plain_result(
                    "comp (比赛) - 竞赛成绩录入(管理员)\n"
                    "格式: /comp[年份] <项目> <姓名> <成绩>\n"
                    "示例: /comp 333 张三 10.5 (默认今年)\n"
                    "示例: /comp24 333 张三 11.2 (指定24年)"
                )
            elif command_word == "ask":
                yield event.plain_result(
                    "ask (查) - 查询成绩\n格式: /ask <项目>\n"
                    "项目: 333/444/num/all等"
                )
            elif command_word == "askwho":
                yield event.plain_result(
                    "askwho (查他) - 查询他人成绩\n格式: /askwho <名字> <项目>"
                )
            elif command_word == "del":
                yield event.plain_result(
                    "del (删) - 删除用户(管理员)\n格式: /del <名字>"
                )
            elif command_word in ("rk", "榜"):
                yield event.plain_result(
                    "rk (榜) - 排行榜\n"
                    "1. 日常榜: /rkd/rkm/rky/rka/rkc <项目> <统计>\n"
                    "   类型: 日/月/年/总/勤奋(rkd/rkm/rky/rka/rkc)\n"
                    "   示例: /rkd 333 ao5\n"
                    "2. 赛事榜: /rk[年份] <项目> <统计>\n"
                    "   示例: /rk24 333 pb (查询24年赛事)\n"
                    "统计: pb(最高) ao5(平均5) mo3(平均3)\n"
                )
        except Exception as e:
            logger.error(f"help error: {e}")

import time
from collections import defaultdict

from click import command
from nonebot.adapters.onebot.v11 import ActionFailed, Bot, GroupMessageEvent
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.typing import T_State
from nonebot_plugin_alconna import Arparma
from nonebot_plugin_saa import Mention, MessageFactory, Text
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import Config
from zhenxun.models.ban_console import BanConsole
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType

malicious_check_time = Config.get_config("hook", "MALICIOUS_CHECK_TIME")
malicious_ban_count = Config.get_config("hook", "MALICIOUS_BAN_COUNT")

if not malicious_check_time:
    raise ValueError("模块: [hook], 配置项: [MALICIOUS_CHECK_TIME] 为空或小于0")
if not malicious_ban_count:
    raise ValueError("模块: [hook], 配置项: [MALICIOUS_BAN_COUNT] 为空或小于0")


class BanCheckLimiter:
    """
    恶意命令触发检测
    """

    def __init__(self, default_check_time: float = 5, default_count: int = 4):
        self.mint = defaultdict(int)
        self.mtime = defaultdict(float)
        self.default_check_time = default_check_time
        self.default_count = default_count

    def add(self, key: str | int | float):
        if self.mint[key] == 1:
            self.mtime[key] = time.time()
        self.mint[key] += 1

    def check(self, key: str | int | float) -> bool:
        if time.time() - self.mtime[key] > self.default_check_time:
            self.mtime[key] = time.time()
            self.mint[key] = 0
            return False
        if (
            self.mint[key] >= self.default_count
            and time.time() - self.mtime[key] < self.default_check_time
        ):
            self.mtime[key] = time.time()
            self.mint[key] = 0
            return True
        return False


_blmt = BanCheckLimiter(
    malicious_check_time,
    malicious_ban_count,
)


# 恶意触发命令检测
@run_preprocessor
async def _(matcher: Matcher, bot: Bot, session: EventSession, state: T_State):
    module = None
    if plugin := matcher.plugin:
        module = plugin.module_name
        if metadata := plugin.metadata:
            extra = metadata.extra
            if extra.get("plugin_type") == PluginType.HIDDEN:
                return
    user_id = session.id1
    group_id = session.id3 or session.id2
    malicious_ban_time = Config.get_config("hook", "MALICIOUS_BAN_TIME")
    if not malicious_ban_time:
        raise ValueError("模块: [hook], 配置项: [MALICIOUS_BAN_TIME] 为空或小于0")
    if user_id:
        if module:
            if _blmt.check(f"{user_id}__{module}"):
                await BanConsole.ban(
                    user_id, group_id, 9, malicious_ban_time * 60, bot.self_id
                )
                logger.info(
                    f"触发了恶意触发检测: {matcher.plugin_name}",
                    "HOOK",
                    session=session,
                )
                await MessageFactory(
                    [
                        Mention(user_id),
                        Text(f"检测到恶意触发命令，您将被封禁 30 分钟"),
                    ]
                ).send()
                logger.debug(
                    f"触发了恶意触发检测: {matcher.plugin_name}",
                    "HOOK",
                    session=session,
                )
                raise IgnoredException("检测到恶意触发命令")
            _blmt.add(f"{user_id}__{module}")

# src/aullbot/context.py
from contextvars import ContextVar
from typing import Optional
from ncatbot.app import BotClient


class RequestContext:
    """存储一次请求（一条消息）所需的全局依赖"""

    def __init__(
        self,
        bot: BotClient,
        chat_type: int,
        chat_id: int | str,
        cache_path: str,
        user_role: str | None,
        sender_id: int | str | None,
        raw_message: str = "",   # 新增：原始消息全文（保留换行）
    ):
        self.bot = bot
        self.chat_type = chat_type
        self.chat_id = chat_id
        self.cache_path = cache_path
        self.user_role = user_role
        self.sender_id = sender_id
        self.raw_message = raw_message   # 存储原始字符串


_current_context: ContextVar[Optional[RequestContext]] = ContextVar(
    "current_context", default=None
)


def set_context(
    bot: BotClient,
    chat_type: int,
    chat_id: int | str,
    cache_path: str,
    user_role: str | None,
    sender_id: int | str | None,
    raw_message: str = "",   # 新增参数
):
    _current_context.set(
        RequestContext(bot, chat_type, chat_id, cache_path, user_role, sender_id, raw_message)
    )


def get_context() -> RequestContext:
    ctx = _current_context.get()
    if ctx is None:
        raise RuntimeError("No context set. Did you forget to call set_context()?")
    return ctx


def get_bot() -> BotClient:
    return get_context().bot


def get_chat_type() -> int:
    return get_context().chat_type


def get_chat_id() -> int | str:
    return get_context().chat_id


def get_cache_path() -> str:
    return get_context().cache_path


def get_user_role() -> str | None:
    return get_context().user_role


def get_sender_id():
    return get_context().sender_id


# 新增：获取原始消息全文
def get_raw_message() -> str:
    return get_context().raw_message
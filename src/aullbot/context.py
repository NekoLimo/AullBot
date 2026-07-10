# scr/context.py
from contextvars import ContextVar
from typing import Optional

class RequestContext:
    """存储一次请求（一条消息）所需的全局依赖"""
    def __init__(self, bot, chat_type, chat_id, cache_path=None):
        self.bot = bot
        self.chat_type = chat_type   # "group: 0"  "private: 1"
        self.chat_id = chat_id
        self.cache_path = cache_path

# 定义上下文变量，默认值为 None
_current_context: ContextVar[Optional[RequestContext]] = ContextVar('current_context', default=None)

def set_context(bot, chat_type, chat_id, cache_path=None):
    """在进入业务处理前，设置当前请求的上下文"""
    _current_context.set(RequestContext(bot, chat_type, chat_id, cache_path))

def get_context() -> RequestContext:
    """获取当前请求的上下文，若未设置则抛出异常"""
    ctx = _current_context.get()
    if ctx is None:
        raise RuntimeError("No context set. Did you forget to call set_context()?")
    return ctx

# 为了方便，还可以提供快捷函数
def get_bot():
    return get_context().bot

def get_chat_type():
    return get_context().chat_type

def get_chat_id():
    return get_context().chat_id

def get_cache_path():
    return get_context().cache_path
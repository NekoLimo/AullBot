# src/aullbot/rbac.py
from functools import wraps
from aullbot import context
from aullbot.history_utils import HistoryManager
from time import time
import inspect

# ---------- 缓存相关 ----------
_config_cache = None
_cache_timestamp = 0
CACHE_TTL = 60  # 缓存60秒

_config_cache_pool = {
    0: {},  # 群聊
    1: {}   # 私聊
}
CACHE_TTL = 60  # 秒

def get_cached_config(chat_id, chat_type):
    """获取配置，每个会话独立 TTL 缓存"""
    now = time()
    item = _config_cache_pool[chat_type].get(chat_id)

    if item and (now - item['ts']) <= CACHE_TTL:
        return item['data']

    new_config = manager.load_config(chat_id=chat_id, chat_type=chat_type)

    _config_cache_pool[chat_type][chat_id] = {
        'data': new_config,
        'ts': now
    }
    return new_config

def invalidate_config_cache():
    """保存配置后调用，使所有缓存失效（强制全部重拉）"""
    global _config_cache_pool

    _config_cache_pool[0].clear()
    _config_cache_pool[1].clear()
    # for v in _config_cache_pool[0].values(): v['ts'] = 0
    # for v in _config_cache_pool[1].values(): v['ts'] = 0

command_manager = {}

ROLE_LEVEL = {"root": 2, "admin": 1, "user": 0, "ALL": -1}
manager = HistoryManager("./bot_data/")


def require_role(required_role, fail_return="No permission"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            chat_config = get_cached_config(
                chat_id=context.get_chat_id(), chat_type=context.get_chat_type()
            )  # 使用缓存读
            sender_id = context.get_sender_id()
            
            if ROLE_LEVEL.get(required_role, 0) > -0.1:
                if sender_id in chat_config.get("blacklist", []):
                    return fail_return

            admin_list = chat_config.get("rbac", {}).get("list", {}).get("admin", [])
            user_list = chat_config.get("rbac", {}).get("list", {}).get("user", [])
            group_role = context.get_user_role() or ""

            if group_role.lower() == "owner":
                sender_id = "$GROUP_OWNER"

            if sender_id in admin_list:
                current_role = "admin"
            else:
                current_role = "user"
                """
                if sender_id not in user_list:
                    chat_config["rbac"]["list"]["user"].append(sender_id)
                    manager.save_config(chat_config)
                """

            if ROLE_LEVEL.get(current_role, -1) < ROLE_LEVEL.get(required_role, -1):
                return fail_return

            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_role_async(required_role, fail_return="No permission"):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            chat_config = get_cached_config(
                chat_id=context.get_chat_id(), chat_type=context.get_chat_type()
            )
            sender_id = context.get_sender_id()

            if sender_id in chat_config.get("blacklist", []):
                return fail_return

            admin_list = chat_config.get("rbac", {}).get("list", {}).get("admin", [])
            group_role = context.get_user_role() or ""

            if group_role.lower() == "owner":
                sender_id = "$GROUP_OWNER"
            if sender_id in admin_list:
                current_role = "admin"
            else:
                current_role = "user"

            if ROLE_LEVEL.get(current_role, -1) < ROLE_LEVEL.get(required_role, -1):
                return fail_return

            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        return wrapper

    return decorator


def group_manager(name):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        command_manager[name] = wrapper
        return wrapper

    return decorator

# src/aullbot/rbac.py
from functools import wraps
from pathlib import Path
from aullbot import context
from aullbot.history_utils import manager
from time import time
import inspect
import json
import os
import re

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


ROOT_FILE = Path(__file__).parents[2] / "bot_data" / "root.json"


def _split_ids(value) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x for x in re.split(r"[,;\s]+", str(value or "")) if x]


def global_roots() -> list[str]:
    """全局 root 列表（aullbot 自己维护，不依赖 ncatbot 的 config.yaml）。

    来源优先级：
      1. 环境变量 AULLBOT_ROOT（.env）
      2. bot_data/root.json  -> {"root": ["123"]} 或 ["123"]
      3. 兜底：ncatbot 配置里的 root（兼容老部署，config.yaml 归 ncatbot 管）

    会话配置里的 rbac.list.root **不参与**——否则群管理员改本群配置
    就能拿到影响整个进程的权限。
    """
    # 1) 环境变量：一旦设置就完全接管（覆盖，不累加）
    env_roots = _split_ids(os.environ.get("AULLBOT_ROOT", ""))
    if env_roots:
        return list(dict.fromkeys(env_roots))

    roots: list[str] = []

    # 2) bot_data/root.json
    try:
        if ROOT_FILE.exists():
            data = json.loads(ROOT_FILE.read_text(encoding="utf-8"))
            roots += _split_ids(data.get("root") if isinstance(data, dict) else data)
    except Exception as e:
        print(f"[rbac] 读取 {ROOT_FILE} 失败: {type(e).__name__}: {e}")

    if not roots:
        try:
            from ncatbot.utils.config import ncatbot_config

            roots += _split_ids(ncatbot_config.root)
        except Exception:
            pass

    # 去重保序
    seen, out = set(), []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def global_root() -> str:
    """第一个全局 root，兼容旧调用。"""
    roots = global_roots()
    return roots[0] if roots else ""


def _resolve_role(chat_config: dict, sender_id, group_role: str = "") -> str:
    """定角色：全局 root > 本会话 admin > user。

    root 只认 config.yaml 的 root（全局），会话配置里的 rbac.list.root 不参与提权，
    否则群管理员改一下本群配置就能拿到全局模块开关权限。
    """
    sid = str(sender_id)

    if sid in global_roots():
        return "root"

    admin_list = [
        str(x) for x in chat_config.get("rbac", {}).get("list", {}).get("admin", [])
    ]
    if sid in admin_list:
        return "admin"
    # 群主自动算本群管理员（模板里的 "$GROUP_OWNER" 占位）
    if str(group_role).lower() == "owner" and "$GROUP_OWNER" in admin_list:
        return "admin"
    return "user"


def validate_role(required_role: str) -> str:
    """装饰器创建时校验角色名，写错立即报错（fail-closed）。

    以前用 ROLE_LEVEL.get(required_role, -1)，把 "admin" 手滑成 "admni"
    会让等级变成 -1 —— 比 user(0) 还低，等于所有人通过。
    """
    if required_role not in ROLE_LEVEL:
        raise ValueError(
            f"未知角色 {required_role!r}，可选: {sorted(ROLE_LEVEL)}"
        )
    return required_role


def blacklist_ids(chat_config: dict) -> set[int]:
    """黑名单统一按 int 比较（配置里可能是 str，容忍脏数据）。"""
    result: set[int] = set()
    for raw in chat_config.get("blacklist", []) or []:
        try:
            result.add(int(raw))
        except (TypeError, ValueError):
            continue
    return result


def is_blacklisted(chat_config: dict, sender_id) -> bool:
    """sender 是否在黑名单里；**root 永远不算**（root 无法被封禁）。"""
    if str(sender_id) in global_roots():
        return False
    try:
        sid = int(sender_id)
    except (TypeError, ValueError):
        return False
    return sid in blacklist_ids(chat_config)


def require_role(required_role, fail_return="No permission"):
    validate_role(required_role)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            chat_config = get_cached_config(
                chat_id=context.get_chat_id(), chat_type=context.get_chat_type()
            )  # 使用缓存读
            sender_id = context.get_sender_id()
            
            if ROLE_LEVEL[required_role] > -0.1 and is_blacklisted(chat_config, sender_id):
                return fail_return

            group_role = context.get_user_role() or ""
            current_role = _resolve_role(chat_config, sender_id, group_role)

            if ROLE_LEVEL.get(current_role, -1) < ROLE_LEVEL[required_role]:
                return fail_return

            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_role_async(required_role, fail_return="No permission"):
    validate_role(required_role)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            chat_config = get_cached_config(
                chat_id=context.get_chat_id(), chat_type=context.get_chat_type()
            )
            sender_id = context.get_sender_id()

            if ROLE_LEVEL[required_role] > -0.1 and is_blacklisted(chat_config, sender_id):
                return fail_return

            group_role = context.get_user_role() or ""
            current_role = _resolve_role(chat_config, sender_id, group_role)

            if ROLE_LEVEL.get(current_role, -1) < ROLE_LEVEL[required_role]:
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

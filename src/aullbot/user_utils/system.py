# src/aullbot/user_utils/system.py
from aullbot.rbac import (
    group_manager,
    require_role,
    invalidate_config_cache,
    get_cached_config,
    command_manager,
    global_roots,
)
from aullbot.history_utils import manager
from aullbot import context
import json


def help_command(cmd: str = None) -> str:  # type: ignore
    """
    help [命令名]
    无参数：列出所有可用命令名称。
    有参数：显示该命令的详细文档。
    """
    if cmd is None or cmd == "":
        cmds = [name for name in command_manager.keys() if name != "help"]
        return "可用命令：\n" + "\n".join(cmds)
    else:
        func = command_manager.get(cmd)
        if func is None:
            return f"未知命令：{cmd}"
        return func.__doc__.strip() if func.__doc__ else "该命令无帮助文档"


@group_manager("clear")
@require_role("admin")
def clear_context():
    """清空ai聊天记录"""
    CHAT_ID = context.get_chat_id()
    CHAT_TYPE = context.get_chat_type()
    manager.save_history(chat_id=CHAT_ID, chat_type=CHAT_TYPE, messages=[])
    return "done"


@group_manager("set-prompt")
@require_role("admin")
def set_prompt(pt: str | None = None):
    """设置ai提示词，无参数清空"""
    CHAT_ID = context.get_chat_id()
    CHAT_TYPE = context.get_chat_type()

    # 使用缓存获取配置（不会重复读磁盘）
    chat_config = get_cached_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE)

    # 检查历史（这一步可能也会读磁盘，看你的 HistoryManager 实现，暂时不改）
    history = manager.read_history(chat_id=CHAT_ID, chat_type=CHAT_TYPE)
    if history:
        return "请清空聊天历史(/clear)"

    # 修改 prompt
    if pt is None or pt == "":
        chat_config["prompt"] = []
    else:
        chat_config["prompt"] = [{"role": "system", "content": pt}]

    # 保存配置
    manager.save_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE, content=chat_config)

    # 重要：保存后使缓存失效，下次调用会重新读取
    invalidate_config_cache()

    return "done"


@group_manager("get-config")
@require_role("user")
def get_config():
    """get-config"""
    CHAT_ID = context.get_chat_id()
    CHAT_TYPE = context.get_chat_type()
    chat_config = get_cached_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE)
    return json.dumps(chat_config, indent=2, ensure_ascii=False)


@group_manager("add-admin")
@require_role("admin")
def add_admin(user: str):
    """add-admin"""
    CHAT_ID = context.get_chat_id()
    CHAT_TYPE = context.get_chat_type()
    chat_config = get_cached_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE)
    if user is None or user == "":
        return "缺失参数\n参数：user: str | qq_number"

    if user in chat_config["rbac"]["list"]["admin"]:
        return "用户已存在"

    chat_config["rbac"]["list"]["admin"].append(user)
    manager.save_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE, content=chat_config)

    # 重要：保存后使缓存失效，下次调用会重新读取
    invalidate_config_cache()

    return "done"


@group_manager("remove-admin")
@require_role("admin")
def remove_admin(user: str):
    """remove-admin"""
    CHAT_ID = context.get_chat_id()
    CHAT_TYPE = context.get_chat_type()
    chat_config = get_cached_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE)
    if user is None or user == "":
        return "未输入参数\n参数：user: str | qq_number"
    if user not in chat_config["rbac"]["list"]["admin"]:
        return "用户不存在"
    chat_config["rbac"]["list"]["admin"].remove(user)
    manager.save_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE, content=chat_config)

    # 重要：保存后使缓存失效，下次调用会重新读取
    invalidate_config_cache()

    return "done"


@group_manager("ban")
@require_role("admin")
def ban(user: str):
    """拉黑某个 QQ（只能存整数；root 不可被封禁）"""
    CHAT_ID = context.get_chat_id()
    CHAT_TYPE = context.get_chat_type()
    chat_config = get_cached_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE)

    raw = (user or "").strip()
    if not raw:
        return "未输入参数\n用法：ban <QQ号>"
    if not raw.isdigit():
        return "QQ 号必须是纯数字（不接受 @、昵称或其它字符）"

    target = int(raw)
    if str(target) in global_roots():
        return "root 不可被封禁"

    # 统一成 int 存储，避免 "123" 与 123 混存导致判定失效
    blacklist = {int(x) for x in chat_config.get("blacklist", []) if str(x).isdigit()}
    if target in blacklist:
        return "用户已存在"

    blacklist.add(target)
    chat_config["blacklist"] = sorted(blacklist)
    manager.save_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE, content=chat_config)

    # 重要：保存后使缓存失效，下次调用会重新读取
    invalidate_config_cache()

    return "done"


@group_manager("unban")
@require_role("admin")
def unban(user: str):
    """解除拉黑（参数为 QQ 号）"""
    CHAT_ID = context.get_chat_id()
    CHAT_TYPE = context.get_chat_type()
    chat_config = get_cached_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE)

    raw = (user or "").strip()
    if not raw:
        return "未输入参数\n用法：unban <QQ号>"
    if not raw.isdigit():
        return "QQ 号必须是纯数字"

    target = int(raw)
    blacklist = {int(x) for x in chat_config.get("blacklist", []) if str(x).isdigit()}
    if target not in blacklist:
        return "用户不存在"

    blacklist.discard(target)
    chat_config["blacklist"] = sorted(blacklist)
    manager.save_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE, content=chat_config)

    # 重要：保存后使缓存失效，下次调用会重新读取
    invalidate_config_cache()

    return "done"


@group_manager("whoami")
@require_role("ALL")
def whoami():
    CHAT_ID = context.get_chat_id()
    CHAT_TYPE = context.get_chat_type()
    SENDER_ID = context.get_sender_id()
    chat_config = get_cached_config(chat_id=CHAT_ID, chat_type=CHAT_TYPE)
    
    if SENDER_ID in chat_config.get("blacklist", []):
        return "Blacklist"
    # root 只看全局（bot_data/root.json 或 AULLBOT_ROOT），会话配置里不再有 root
    if str(SENDER_ID) in global_roots():
        return "Root"
    if SENDER_ID in chat_config.get("rbac", {}).get("list", {}).get("admin", []):
        return "Admin"
    return "User"
# src/aullbot/tools/myplugin.py
"""
写点杂的
"""

from aullbot.command_registry import command, ai_tools
from aullbot.rbac import require_role
from aullbot.context import get_chat_type, get_chat_id
from requests import get

# src/aullbot/tools/myplugin.py 顶部加
from aullbot.module_meta import ModuleMeta

MODULE = ModuleMeta(
    name="myplugin",
    author="Limo",
    description="杂项插件：震动设备等",
    default_enabled=True,
    tags=("misc",),
)

@ai_tools("vibrate")
@command("/震动")
@require_role("user")
def vibrate(time: int = None):
    chat_type = get_chat_type()
    chat_id = int(get_chat_id())
    """震动设备，单位:ms"""
    if time is None or time == "":
        time = 500
    try:
        time = int(time)
    except (TypeError, ValueError):
        return "参数错误"
    try:
        resp = get(f"http://127.0.0.1:1145/vib/{time}/{chat_type}/{chat_id}")
    except Exception:
        return "服务未启动"
    return str(resp.json())


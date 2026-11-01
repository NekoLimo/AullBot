# src/aullbot/tools/module_admin.py
from aullbot.module_meta import ModuleMeta
from aullbot.command_registry import command, ai_tools
from aullbot.rbac import require_role_async
from aullbot.module_manager import mm

MODULE = ModuleMeta(
    name="module_admin",
    author="Limo",
    description="模块管理（热开关）",
    default_enabled=True,
    tags=("core", "admin"),
    readme="""
/module list                列出所有模块及状态
/module info <name>         查看某模块详情
/module enable <name>       热开启
/module disable <name>      热禁用
/module sync                刷新 manifest

权限：root（全局操作）。
admin 只是"本会话最高权限"，不足以开关影响整个进程的模块。
""",
)


@command("/module")
@require_role_async("root")   # 全局开关，必须全局权限；admin 是本会话最高权限，不够
async def module_admin(args: str = "") -> str:
    """模块管理：/module [list | info <name> | enable <name> | disable <name> | sync]"""
    parts = args.split()
    if not parts or parts[0] == "list":
        return mm.list_modules()

    sub = parts[0]
    if sub == "info" and len(parts) == 2:
        return mm.info(parts[1])
    if sub == "enable" and len(parts) == 2:
        return await mm.enable(parts[1])
    if sub == "disable" and len(parts) == 2:
        return await mm.disable(parts[1])
    if sub == "sync":
        s = mm.sync_manifest()
        if not any(s.values()):
            return "manifest 与代码一致，无变更"
        return (
            f"manifest 已更新\n"
            f"新增：{s['added'] or '无'}\n"
            f"移除：{s['removed'] or '无'}\n"
            f"变更：{s['changed'] or '无'}"
        )
    return (
        "用法：/module [list | info <name> | enable <name> | "
        "disable <name> | sync]"
    )


@ai_tools("list_modules")
@require_role_async("root")
async def list_modules_tool() -> str:
    """列出所有模块及其启用状态"""
    return mm.list_modules()


@ai_tools("toggle_module")
@require_role_async("root")
async def toggle_module(name: str, enable: bool) -> str:
    """开启或禁用模块。参数：name 模块名，enable 是否启用"""
    return await (mm.enable(name) if enable else mm.disable(name))
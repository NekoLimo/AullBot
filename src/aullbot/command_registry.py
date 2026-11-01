# src/aullbot/command_registry.py
import sys
from aullbot.module_manager import mm

command_registry = {}
command_tools = {}


def _owner_of(func) -> str | None:
    mod = sys.modules.get(func.__module__)
    if mod is None:
        return None
    meta = getattr(mod, "MODULE", None)
    return getattr(meta, "name", None) if meta else None


def command(name):
    def decorator(func):
        owner = _owner_of(func)
        if owner is None:
            print(f"[command] {func.__module__}.{func.__qualname__} 未定义 MODULE，拒绝注册 {name}")
            return func
        command_registry[name] = func
        mm.bind_command(owner, name)
        return func
    return decorator


def ai_tools(name):
    def decorator(func):
        owner = _owner_of(func)
        if owner is None:
            print(f"[ai_tools] {func.__module__}.{func.__qualname__} 未定义 MODULE，拒绝注册 {name}")
            return func
        command_tools[name] = func
        mm.bind_tool(owner, name)
        return func
    return decorator
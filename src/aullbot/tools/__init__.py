# src/aullbot/tools/__init__.py
import ast
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any, Dict, List

from aullbot.command_registry import (  # noqa: F401  这里 re-export 供模块导入
    command_registry,
    command_tools,
    command,
    ai_tools,
)
from aullbot.module_manager import mm


# ---------- AST 预检查：顶层是否声明了 MODULE ----------
def _has_module_decl(path: Path) -> tuple[bool, str]:
    """只检查文件顶层（tree.body 直属）的 MODULE 赋值。
    支持 MODULE = ... 和 MODULE: ModuleMeta = ... 两种写法。
    返回 (是否存在, 说明文本)。"""
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"读取失败: {e}"
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return False, f"语法错误: 第 {e.lineno} 行 {e.msg}"
    except Exception as e:
        return False, f"AST 解析失败: {e}"

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "MODULE":
                    return True, f"第 {node.lineno} 行"
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "MODULE":
                return True, f"第 {node.lineno} 行"
    return False, "顶层未发现 MODULE 赋值"


# ---------- 自动扫描 tools/ 下所有模块 ----------
_pkg_path = Path(__file__).parent
_pending_registers: list = []   # 收集模块的 register(bot) 回调，等 bot 就绪后调

for _info in pkgutil.iter_modules([str(_pkg_path)]):
    if _info.name.startswith("_"):
        continue

    _py_path = _pkg_path / f"{_info.name}.py"
    _ok, _why = _has_module_decl(_py_path)
    if not _ok:
        print(f"[tools] {_info.name}.py 跳过（{_why}）")
        continue

    try:
        _mod = importlib.import_module(f"aullbot.tools.{_info.name}")
    except Exception as e:
        import traceback
        print(f"[tools] 加载 {_info.name} 失败: {e}")
        traceback.print_exc()
        continue

    meta = getattr(_mod, "MODULE", None)
    if meta is None:
        # AST 说顶层有赋值，import 后却拿不到——通常是条件赋值或写进了类体
        print(f"[tools] {_info.name}.py 顶层有 MODULE 但 import 后读不到，跳过")
        continue

    mm.register(meta, source_file=f"tools/{_info.name}.py")
    if hasattr(_mod, "register"):
        _pending_registers.append(_mod.register)


# ---------- 元命令（直接赋值，不走装饰器，永远可用）----------
def _describe(func) -> str:
    """命令签名（含返回类型）+ 文档字符串，例如 base64_encode(text: str) -> str。"""
    try:
        sig = str(inspect.signature(func))
    except (TypeError, ValueError):
        sig = "(...)"
    lines = [f"{getattr(func, '__name__', '?')}{sig}"]
    doc = (func.__doc__ or "").strip()
    if doc:
        lines.append(doc)
    return "\n".join(lines)


def help_command(cmd: str = None) -> str:  # type: ignore
    """
    help [命令名]
    无参数：列出所有可用命令名称。
    有参数：显示该命令的签名与详细文档（带不带 / 都可以）。
    """
    if cmd is None or cmd == "":
        cmds = [name for name in command_registry.keys() if name != "/help"]
        return "可用命令：\n" + "\n".join(cmds)
    key = cmd.strip()
    func = command_registry.get(key) or command_registry.get("/" + key.lstrip("/"))
    if func is None:
        return f"未知命令：{cmd}"
    return _describe(func)


def help_ai_tools(tool: str = None) -> str:  # type: ignore
    """
    help_ai_tools [工具名]
    无参数：列出所有可用 AI 工具名称。
    有参数：显示该工具的详细文档。
    """
    if tool is None or tool == "":
        return "可用 AI 工具：\n" + "\n".join(command_tools.keys())
    func = command_tools.get(tool.strip())
    if func is None:
        return f"未知 AI 工具：{tool}"
    return _describe(func)


command_registry["/help"] = help_command
command_tools["get_help"] = help_ai_tools
command_route: dict[str, Any] = command_registry
ai_tools_map: dict[str, Any] = command_tools


# ---------- 生成 AI 工具规范（按模块启用状态过滤）----------
def generate_ai_tools_spec() -> List[Dict[str, Any]]:
    tools = []
    for tool_name, func in ai_tools_map.items():
        if not mm.is_tool_enabled(tool_name):
            continue
        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": func.__doc__.strip() if func.__doc__ else f"工具 {tool_name}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        sig = inspect.signature(func)
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            ann = param.annotation
            if ann is str or ann == inspect.Parameter.empty:
                param_type = "string"
            elif ann is int:
                param_type = "integer"
            elif ann is float:
                param_type = "number"
            elif ann is bool:
                param_type = "boolean"
            elif ann is list:
                param_type = "array"
            else:
                param_type = "string"
            prop: Dict[str, Any] = {"type": param_type, "description": f"参数 {param_name}"}
            if param_type == "array":
                prop["items"] = {"type": "string"}
            tool["function"]["parameters"]["properties"][param_name] = prop
            if param.default == inspect.Parameter.empty:
                tool["function"]["parameters"]["required"].append(param_name)
        tools.append(tool)
    return tools
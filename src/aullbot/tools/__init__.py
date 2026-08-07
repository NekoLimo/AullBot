# src/aullbot/tools/__init__.py
from typing import Any, List, Dict
import inspect
import json
from . import system, play_music, tts, msg_tools, myplugin
from aullbot.command_registry import command_registry, command_tools
from .system import help_command

command_registry["/help"] = help_command
command_tools["get_help"] = system.help_ai_tools

command_route: dict[str, Any] = command_registry
ai_tools_map: dict[str, Any] = command_tools

__all__ = list(command_registry.keys()) + ["command_route", "help_command"] # type: ignore

# ------------------------------------------------------------
# 以下是新增的 tools 列表生成器
# ------------------------------------------------------------

def generate_ai_tools_spec() -> List[Dict[str, Any]]:
    """
    遍历 ai_tools_map，生成符合 OpenAI/DeepSeek Function Calling 规范的 tools 列表。
    返回的列表可直接用于 client.chat.completions.create(tools=...)
    """
    tools = []

    for tool_name, func in ai_tools_map.items():
        # 基础结构
        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": func.__doc__.strip() if func.__doc__ else f"工具 {tool_name}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                }
            }
        }

        # 解析函数签名
        sig = inspect.signature(func)
        params = sig.parameters

        for param_name, param in params.items():
            # 忽略 self/cls（不期望出现）
            if param_name in ('self', 'cls'):
                continue

            # 映射参数类型到 JSON Schema 类型
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
                # 其他复杂类型默认当作 string（安全起见）
                param_type = "string"

            # 构造属性描述
            prop: Dict[str, Any] = {
                "type": param_type,
                "description": f"参数 {param_name}"  # 简单描述，可进一步从 docstring 提取
            }

            # 如果类型是 array，指定 items（假设元素是 string）
            if param_type == "array":
                prop["items"] = {"type": "string"}

            # 判断是否必填（没有默认值即为必填）
            is_required = param.default == inspect.Parameter.empty

            # 加入 properties
            tool["function"]["parameters"]["properties"][param_name] = prop
            if is_required:
                tool["function"]["parameters"]["required"].append(param_name)

        tools.append(tool)

    return tools

# 可选：增加一个调试打印函数，方便查看生成的 JSON
def print_ai_tools_spec():
    """打印格式化的 tools JSON，用于调试"""
    spec = generate_ai_tools_spec()
    print(json.dumps(spec, indent=2, ensure_ascii=False))
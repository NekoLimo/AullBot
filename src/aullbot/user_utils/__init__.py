# src/aullbot/user_utils/__init__.py
from aullbot.rbac import command_manager
from .system import help_command
from typing import Any

command_manager["help"] = help_command


command_manager_map: dict[str, Any] = command_manager

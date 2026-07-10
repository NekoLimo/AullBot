# private_plugins/__init__.py
from . import system
from . import play_music
from . import jmbb
from .command_registry import command_registry
from .system import help_command   

command_registry["help"] = help_command

command_route = command_registry

__all__ = list(command_registry.keys()) + ["command_route", "help_command"]

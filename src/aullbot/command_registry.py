# src/aullbot/command_registry.py

command_registry = {}
command_tools = {}


def command(name):
    """装饰器：将函数注册为命令，名称为 name"""

    def decorator(func):
        command_registry[name] = func
        return func

    return decorator


def ai_tools(name):
    """装饰器：将函数注册为 AI 工具，名称为 name"""

    def decorator(func):
        command_tools[name] = func
        return func

    return decorator

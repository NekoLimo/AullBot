# private_plugins/command_registry.py
command_registry = {}

def command(name):
    """装饰器：将函数注册为命令，名称为 name"""
    def decorator(func):
        command_registry[name] = func
        return func
    return decorator
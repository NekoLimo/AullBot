# src/aullbot/tools/bot_status.py
"""机器人状态（自检死活用）。

单独成模块，随时可以用 `/module disable bot_status` 关掉，不影响其它功能。
"""
import platform
import time
from pathlib import Path

from aullbot.module_meta import ModuleMeta
from aullbot.command_registry import command
from aullbot.rbac import require_role
from aullbot import context

MODULE = ModuleMeta(
    name="bot_status",
    author="Limo",
    description="机器人状态：版本 / 平台 / 运行时长",
    version="1.0.0",
    default_enabled=True,
    tags=("core", "status"),
    readme="""
命令：
  #aull   显示版本、平台、系统和架构、运行时长

版本从项目根目录的 .aullver 读取（读不到则回退 pyproject.toml）。
运行时长从进程启动开始算。

这个模块不做任何网络请求，纯粹用来确认 bot 还活着；
不需要的话 `/module disable bot_status` 即可关闭。
""",
)

# src/aullbot/tools/bot_status.py -> 仓库根目录
BASE_DIR = Path(__file__).parents[3]

# 模块在 aullbot.tools 导入时加载，约等于进程启动时刻
START_TS = time.time()

VERSION_FILES = (".aullver", "VERSION", "version.txt")


def _read_version() -> str:
    """优先 .aullver，其次 pyproject.toml。"""
    for name in VERSION_FILES:
        path = BASE_DIR / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if text:
            return text
    try:
        import tomllib

        with (BASE_DIR / "pyproject.toml").open("rb") as f:
            return "v" + str(tomllib.load(f)["project"]["version"])
    except Exception:
        return "未知"


def _platform(bot) -> str:
    """从适配器取平台名，退而取已注册的 API 平台。"""
    names: list[str] = []
    try:
        for adapter in getattr(bot, "_adapters", None) or []:
            name = getattr(adapter, "platform", None) or getattr(adapter, "name", None)
            if name:
                names.append(str(name))
    except Exception:
        pass
    if not names:
        try:
            api = getattr(bot, "api", None)
            names = [str(x) for x in (getattr(api, "_platforms", {}) or {})]
        except Exception:
            pass
    # 去重保序
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return ", ".join(seen) if seen else "未知"


ARCH_MAP = {
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "armv7",
    "armv8l": "arm64",
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "i386": "x86",
    "i686": "x86",
}


def _system_arch() -> str:
    """只给系统和架构，不带内核版本和发行版。"""
    system = (platform.system() or "").strip() or "未知"
    machine = (platform.machine() or "").strip().lower()
    return f"{system} {ARCH_MAP.get(machine, machine or '未知')}"


def _uptime_text(seconds: float) -> str:
    """15分钟 36秒 / 2小时 5分钟 / 1天 3小时。"""
    total = max(0, int(seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分钟")
    if secs or not parts:
        parts.append(f"{secs}秒")
    return " ".join(parts)


def _render(bot) -> str:
    return "\n".join([
        "bot 状态",
        f"版本: {_read_version()}",
        f"平台: {_platform(bot)}",
        f"系统和架构: {_system_arch()}",
        f"运行时长: {_uptime_text(time.time() - START_TS)}",
        "Power by AullBot",
        "/module disable bot_status 关闭此功能"
    ])


@command("#aull")
@require_role("user")
def bot_status(args: str = "") -> str:
    """查看 bot 状态：版本 / 平台 / 系统和架构 / 运行时长"""
    try:
        bot = context.get_bot()
    except Exception:
        bot = None
    return _render(bot)

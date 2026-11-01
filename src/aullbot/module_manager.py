# src/aullbot/module_manager.py
import asyncio
import json
from pathlib import Path

from aullbot.module_meta import ModuleMeta

# 绝对路径：换目录启动也能找到数据（与 history_utils 保持一致）
BOT_DATA = Path(__file__).resolve().parents[2] / "bot_data"
CONFIG_PATH = BOT_DATA / "modules.json"
MANIFEST_PATH = BOT_DATA / "modules_manifest.json"


class Module:
    def __init__(self, meta: ModuleMeta):
        self.meta = meta
        self.name = meta.name
        self.enabled = meta.default_enabled  # 运行时状态，可被覆盖
        self.config: dict = {}
        self.tasks: list[asyncio.Task] = []  # 后台任务
        self._on_load = None
        self._on_unload = None

    def on_load(self, fn):
        """注册加载回调，签名 async def fn(module, bot)"""
        self._on_load = fn
        return fn

    def on_unload(self, fn):
        """注册卸载回调，签名 async def fn(module)"""
        self._on_unload = fn
        return fn

    def spawn(self, coro):
        """创建后台任务，disable 时自动 cancel；结束后自动从列表移除。"""
        task = asyncio.create_task(coro)
        self.tasks.append(task)

        def _prune(done: asyncio.Task) -> None:
            try:
                self.tasks.remove(done)
            except ValueError:
                pass

        task.add_done_callback(_prune)
        return task


class ModuleManager:
    def __init__(self):
        self.modules: dict[str, Module] = {}
        self.command_owner: dict[str, str] = {}  # 命令名 -> 模块名
        self.tool_owner: dict[str, str] = {}  # 工具名 -> 模块名
        self.bot = None
        self.config: dict[str, dict] = {}
        self._load_config()

    # ---------- 配置持久化 ----------
    def _load_config(self):
        if CONFIG_PATH.exists():
            try:
                self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                self.config = {}
        else:
            self.config = {}

    def save_config(self, name: str):
        m = self.modules[name]
        self.config.setdefault(name, {})
        self.config[name]["enabled"] = m.enabled
        self.config[name]["config"] = m.config
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    def sync_manifest(self) -> dict:
        """扫描当前已注册模块，写一份清单文件并返回 diff。"""
        new = {
            name: {
                "name": m.meta.name,
                "author": m.meta.author,
                "description": m.meta.description,
                "version": m.meta.version,
                "default_enabled": m.meta.default_enabled,
                "tags": list(m.meta.tags),
                "requires": list(m.meta.requires),
                "source_file": getattr(m, "source_file", ""),
            }
            for name, m in self.modules.items()
        }
        old = {}
        if MANIFEST_PATH.exists():
            try:
                old = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            except Exception:
                old = {}
        added   = [k for k in new if k not in old]
        removed = [k for k in old if k not in new]
        changed = [k for k in new if k in old and new[k] != old[k]]
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(new, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"added": added, "removed": removed, "changed": changed}

    # ---------- 注册 ----------
    def register(self, meta: ModuleMeta, source_file: str = "") -> Module:
        if meta.name in self.modules:
            return self.modules[meta.name]
        m = Module(meta)
        m.source_file = source_file
        cfg = self.config.get(meta.name, {})
        m.enabled = cfg.get("enabled", meta.default_enabled)  # 配置文件优先
        m.config = cfg.get("config", {})
        self.modules[meta.name] = m
        return m

    def bind_command(self, module_name: str, command_name: str):
        self.command_owner[command_name] = module_name

    def bind_tool(self, module_name: str, tool_name: str):
        self.tool_owner[tool_name] = module_name

    # ---------- 路由检查 ----------
    def is_command_enabled(self, command_name: str) -> bool:
        owner = self.command_owner.get(command_name)
        if owner is None:
            return True
        m = self.modules.get(owner)
        return m is not None and m.enabled

    def is_tool_enabled(self, tool_name: str) -> bool:
        owner = self.tool_owner.get(tool_name)
        if owner is None:
            return True
        m = self.modules.get(owner)
        return m is not None and m.enabled

    def get_module_config(self, name: str) -> dict:
        m = self.modules.get(name)
        return m.config if m else {}

    # ---------- 热开关 ----------
    async def enable(self, name: str) -> str:
        m = self.modules.get(name)
        if not m:
            return f"Unknown module: {name}"
        if m.enabled:
            return f"Module {name} is enabled"
        missing = [
            d
            for d in m.meta.requires
            if d not in self.modules or not self.modules[d].enabled
        ]
        if missing:
            return f"Can't enable {name}：Dependency not enabled: {', '.join(missing)}"
        m.enabled = True
        try:
            if m._on_load:
                await m._on_load(m, self.bot)
        except Exception as e:
            # 回滚：内存里已置 True，但回调失败 → 恢复原状，避免"重启后自己变回来"
            m.enabled = False
            for t in list(m.tasks):
                if not t.done():
                    t.cancel()
            m.tasks.clear()
            return f"启用 {name} 失败（已回滚）: {type(e).__name__}: {e}"
        self.save_config(name)
        return f"Module {name} is enabled"

    async def disable(self, name: str) -> str:
        m = self.modules.get(name)
        if not m:
            return f"Unknown module: {name}"
        if not m.enabled:
            return f"Module {name} is disabled"
        m.enabled = False
        for t in list(m.tasks):
            if not t.done():
                t.cancel()
        m.tasks.clear()
        try:
            if m._on_unload:
                await m._on_unload(m)
        except Exception as e:
            # 回滚为启用状态，避免"明明禁用失败却显示已禁用"
            m.enabled = True
            return f"禁用 {name} 失败（已回滚）: {type(e).__name__}: {e}"
        self.save_config(name)
        return f"Module {name} is disabled"

    async def load_all(self, bot):
        """启动时调用：对所有已启用的模块触发 on_load"""
        self.bot = bot
        for m in self.modules.values():
            if m.enabled and m._on_load:
                try:
                    await m._on_load(m, bot)
                except Exception as e:
                    print(f"[ModuleManager] Failed to load module {m.name} : {e}")

    # ---------- 展示 ----------
    def list_modules(self) -> str:
        """紧凑列表：只列模块名，按启用/禁用分组，避免 QQ 长行换行。

        描述去 /module info <name> 看。
        """
        enabled = [m.meta.name for m in self.modules.values() if m.enabled]
        disabled = [m.meta.name for m in self.modules.values() if not m.enabled]
        if not enabled and not disabled:
            return "没有已注册的模块"

        def wrap(names: list[str], width: int = 28) -> list[str]:
            lines, cur = [], ""
            for name in names:
                if cur and len(cur) + 1 + len(name) > width:
                    lines.append(cur)
                    cur = name
                else:
                    cur = f"{cur} {name}".strip()
            if cur:
                lines.append(cur)
            return lines

        out = [f"模块 {len(enabled) + len(disabled)} 个"
               f"（启用 {len(enabled)} / 禁用 {len(disabled)}）", ""]
        if enabled:
            out.append("启用：")
            out.extend(f"  {line}" for line in wrap(enabled))
        if disabled:
            out.append("禁用：")
            out.extend(f"  {line}" for line in wrap(disabled))
        out += ["", "/module info <name> 查看详情"]
        return "\n".join(out)

    def commands_of(self, name: str) -> list[str]:
        return [c for c, o in self.command_owner.items() if o == name]

    def tools_of(self, name: str) -> list[str]:
        return [t for t, o in self.tool_owner.items() if o == name]

    def info(self, name: str) -> str:
        m = self.modules.get(name)
        if not m:
            return f"未知模块: {name}"
        meta = m.meta
        lines = [
            f"{meta.name}  v{meta.version}",
            f"author：{meta.author}",
            f"status：{'Enable' if m.enabled else 'Disable'}（default {'Enable' if meta.default_enabled else 'Disable'}）",
            f"description：{meta.description}",
        ]
        cmds = self.commands_of(name)
        if cmds:
            lines.append(f"command：{', '.join(cmds)}")
        tools = self.tools_of(name)
        if tools:
            lines.append(f"AI tools：{', '.join(tools)}")
        if meta.readme:
            lines += ["", "── README ──", meta.readme.strip()]
        return "\n".join(lines)


mm = ModuleManager()

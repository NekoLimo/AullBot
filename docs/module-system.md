# 模块系统

## 1. 三个核心对象

| 对象 | 位置 | 作用 |
|---|---|---|
| `ModuleMeta` | `module_meta.py` | 模块的**声明**（元数据、默认开关、配置 schema、readme） |
| `Module` | `module_manager.py` | 模块的**运行时状态**（是否启用、后台任务列表、on_load 回调） |
| `mm` | `module_manager.py` 末尾的单例 | 全局管理器，注册表 + 热开关 + 归属查询 |

## 2. ModuleMeta 字段

```python
@dataclass
class ModuleMeta:
    name: str                    # 唯一标识，必填
    author: str = ""
    description: str = ""
    version: str = "1.0.0"
    default_enabled: bool = True
    tags: tuple = ()
    requires: tuple = ()         # 依赖的其它模块名，禁用时会检查
    config_schema: dict = {}     # 配置项声明，见下
    readme: str = ""             # /module info 会显示
```

### config_schema

声明配置的默认值和类型，`/module info` 与模块自己读配置时会用到：

```python
config_schema={
    "interval": {"type": "int", "default": 45, "desc": "轮询间隔（秒）"},
    "include_video": {"type": "bool", "default": True, "desc": "是否监控投稿"},
}
```

读取方式（推荐自己合并默认值）：

```python
def _cfg() -> dict:
    cfg = {k: v["default"] for k, v in (MODULE.config_schema or {}).items()
           if isinstance(v, dict) and "default" in v}
    mod = mm.modules.get(MODULE.name)
    if mod and isinstance(mod.config, dict):
        cfg.update(mod.config)     # modules.json 里的值覆盖默认值
    return cfg
```

## 3. 注册流程

```python
# tools/__init__.py 做三件事：
1. glob("tools/*.py")
2. AST 预检查：文件里有没有 `MODULE = ModuleMeta(...)`
     没有 → 打印 [tools] 跳过 xxx.py（未声明 MODULE）并忽略该文件
3. importlib 加载
     → 模块内的 @command / @ai_tools 在导入时立即注册
     → mm.register(meta, source_file) 记录归属
     → 若模块有 register(bot) 函数，收集到 _pending_registers
```

**为什么用 AST 预检查**：直接 import 一个没写 `MODULE` 的文件，它的 `@command` 会被
`command_registry._owner_of()` 拒绝并打印告警，但文件里的其它副作用（起线程、读文件）已经发生了。
预检查能在导入前就跳过。

## 4. 模块归属

命令和 AI 工具都会记录「属于哪个模块」：

```python
mm.command_owner["/say"]      # -> "basics"
mm.tool_owner["bili_subscribe"]  # -> "bilibili_monitor"
```

`find_command` 每次执行前都会查：

```python
if command_name not in UNGUARDED_COMMANDS and not mm.is_command_enabled(command_name):
    owner = mm.command_owner.get(command_name, "未知模块")
    ...
```

`UNGUARDED_COMMANDS = frozenset({"/module"})` —— 保证不会因为禁用 `module_admin`
把开关自己锁死。

## 5. 生命周期钩子

```python
def register(bot):
    mod = mm.modules.get(MODULE.name)
    if mod is None:
        return                      # 模块没注册成功（多半是导入失败）

    @mod.on_load
    async def _on_load(m, bot_):    # 签名固定：async def fn(module, bot)
        m.spawn(_loop(bot_))        # 起后台任务

    @mod.on_unload
    async def _on_unload(m):        # 可选
        print("清理资源")
```

`mod.spawn(coro)` 会把任务记进 `m.tasks`，`/module disable` 时自动 `cancel()`：

```python
async def disable(self, name):
    m.enabled = False
    for t in m.tasks:
        if not t.done():
            t.cancel()
    m.tasks.clear()
```

> 所以后台循环里必须写 `except asyncio.CancelledError: raise`，
> 否则取消不掉、任务变成僵尸。

## 6. 热开关

```python
await mm.disable("bilibili_monitor")   # 命令立即失效 + 后台任务被取消
await mm.enable("bilibili_monitor")    # 恢复
```

命令层入口是 `/module`（`tools/module_admin.py`）：

```
/module list                 列出模块与状态
/module info <name>          详情（含 readme、命令、工具、配置）
/module enable <name>        热开启
/module disable <name>       热禁用
/module sync                 重新扫描并刷新 manifest
```

状态持久化在 `bot_data/modules.json`：

```json
{
  "bilibili_monitor": {
    "enabled": true,
    "config": { "interval": 45, "video_every": 1 }
  }
}
```

只有被开关过或写过配置的模块才会出现在这个文件里；没出现的模块用代码里的默认值。

## 7. 依赖检查

`ModuleMeta.requires` 声明依赖：

```python
MODULE = ModuleMeta(name="bili_report", requires=("bilibili_monitor",))
```

`mm.enable()` 会检查依赖是否都已启用，未满足则拒绝开启。

## 8. 写模块的完整清单

- [ ] 文件放在 `src/aullbot/tools/`，文件名小写
- [ ] 文件顶层有 `MODULE = ModuleMeta(...)`（否则整个文件被跳过）
- [ ] `name` 唯一，且和文件名一致（便于排查）
- [ ] 命令用 `@command("/xxx")`，必须配 `@require_role` 或 `@require_role_async`
- [ ] AI 工具用 `@ai_tools("xxx")`，函数要有清晰 docstring（模型靠它决定是否调用）
- [ ] 后台任务放 `mod.on_load` 里，用 `m.spawn(...)` 创建
- [ ] 循环里写 `except asyncio.CancelledError: raise`
- [ ] 不在导入阶段做网络请求

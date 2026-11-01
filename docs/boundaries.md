# 边界：框架层 vs 模块层

> **一句话：模块是别人写的，框架是维护者写的。写模块的人不要动框架。**

## 1. 两层划分

```
src/aullbot/                  ← 框架层（维护者负责）
├── main.py                   事件入口、命令分发
├── module_manager.py         模块系统
├── module_meta.py            ModuleMeta
├── command_registry.py       @command / @ai_tools
├── rbac.py                   权限
├── context.py                请求上下文
├── push.py                   主动推送
├── chat.py                   AI 会话
├── history_utils.py          历史与配置读写
└── user_utils/               /manager 等内置命令

src/aullbot/tools/            ← 模块层（谁来写都行）
├── basics.py
├── bilibili_monitor.py
├── bot_status.py
└── ...
```

## 2. 各自能做什么

| | 框架层 | 模块层 |
|---|---|---|
| 谁能改 | 框架维护者 | 任何人 |
| 放什么 | 命令分发、权限、推送、上下文、AI 循环 | 具体功能（命令、工具、后台任务） |
| 新增文件 | 需要评审(如果pr) | 直接加(不pr主仓库) |
| 改动影响 | 全局，可能影响所有模块 | 只影响自己 |

__(当然，如果你不pr到主仓库那就随便改)__

## 3. 模块作者可用的扩展点（只有这些）

```python
# 1. 声明模块
from aullbot.module_meta import ModuleMeta
MODULE = ModuleMeta(name="xxx", ...)

# 2. 注册命令
from aullbot.command_registry import command
@command("/xxx")

# 3. 注册 AI 工具
from aullbot.command_registry import ai_tools
@ai_tools("xxx")

# 4. 权限
from aullbot.rbac import require_role, require_role_async

# 5. 当前会话
from aullbot import context
context.get_chat_id() / get_chat_type() / get_sender_id() / get_raw_message()

# 6. 主动推送（后台/定时任务）
from aullbot import push
await push.send_group(...) / send_many(...) / send_forward(...)

# 7. 模块生命周期
mm.modules[MODULE.name].on_load / on_unload / spawn

# 8. 自己的配置
mm.get_module_config(MODULE.name)
```

**这些以外的最好不要碰** 包括但不限于：

- 不要改 `find_command` 的参数分发规则
- 不要改 `require_role` 的判定逻辑
- 不要在 `main.py` 里加特判
- 不要改 `push` 的接口约定
- 不要给 `context` 加全局变量来跨模块传值

## 4. 需要框架改动怎么办

如果你在写模块时发现"框架少了个能力"，走这条路：

1. 在 issue / 群里说明场景（要做什么、现在为什么做不到）
2. 维护者决定加不加
3. 加了之后更新本文件与相关文档
4. 你再用新能力改模块
5.没人回，使用特性(!?绕过?!)

### 设计特性（不是 bug，别去"修"）

| 行为 | 设计意图 |
|---|---|
| 多参数命令超出部分被丢弃 | 命令语义是"定长参数"，要长文本用单参数或 `context.get_raw_message()` |
| 布尔参数从消息传是字符串 | 消息本质是文本，`"false"` 是 truthy；布尔只对代码调用有意义 |
| 空消息触发 IndexError | 被兜底吞掉，返回 `COMMAND_NOT_FOUND`，不影响功能 |

这三条以前被当成"粗糙点"，其实都是**有意的设计**。改掉反而会破坏现有命令的语义。

### root 与 admin 的边界

| 角色 | 范围 | 来源 |
|---|---|---|
| `root` | **全局** | `config.yaml` 的 `root` 字段，**唯一来源** |
| `admin` | **本聊天会话最高** | 会话配置 `rbac.list.admin`，群主自动算 |

推论：

```python
@command("/module")
@require_role_async("root")     # ✅ 全局开关，要全局权限
```

**会话配置里的 `rbac.list.root` 不参与提权**——否则群管理员改一下本群配置，
就能拿到影响整个进程的模块开关权限。

```python
# rbac._resolve_role()
root_id = global_root()                  # 只认 config.yaml
if sid == root_id:
    return "root"
if sid in admin_list or (群主 and "$GROUP_OWNER" in admin_list):
    return "admin"
return "user"
```

### 关于私聊权限（不是问题）

私聊一律按会话最高权限（`owner`）处理，是**有意设计**：每个私聊是独立会话，
有自己的提示词，陌生人只能改他自己的那份，影响不到别人。

前提是 **admin 命令必须只作用于本会话**；任何全局操作都必须用 `root`。

| 命令 | 级别 | 作用域 |
|---|---|---|
| `/set-prompt` 等 | admin | 本会话 |
| `/module enable\|disable` | **root** | 全局 |

## 5. 代码评审清单

提交模块时，维护者只检查这些：

- [ ] 只动了 `src/aullbot/tools/` 下的文件
- [ ] 有 `MODULE = ModuleMeta(...)`
- [ ] 命令都带权限装饰器
- [ ] 后台任务用 `mod.spawn`，循环里 `except asyncio.CancelledError: raise`
- [ ] 没有在导入阶段做网络请求
- [ ] 没有依赖私有字段（下划线开头）作为长期契约

## 6. 为什么这样分

- **框架是单点**：命令分发、权限、推送的 bug 修一次就全好了
- **模块是多个点**：各写各的，互不影响，坏一个不拖垮全局
- **接口稳定**：模块只依赖上面列出的扩展点，框架内部重构不破坏模块

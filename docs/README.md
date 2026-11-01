# AullBot 框架文档

> 一个基于 [ncatbot](https://github.com/ncatbot/ncatbot) 的 QQ 机器人框架，
> 核心是「模块化 + 命令/工具双路由 + 可热插拔」。
>
> **框架层（`src/aullbot/*.py`）由维护者修改，模块作者只在 `src/aullbot/tools/` 下写，
> 详见 [边界](boundaries.md)。**

## 文档索引

| 文档 | 内容 | 适合谁 |
|---|---|---|
| [**边界：框架 vs 模块**](boundaries.md) | **谁能改什么，扩展点有哪些** | **写模块前必读** |
| [架构总览](architecture.md) | 分层、消息流、启动流程 | 先读 |
| [模块系统](module-system.md) | `ModuleMeta` / 注册 / 热开关 / 生命周期 | 写模块前必读 |
| [命令](commands.md) | `@command`、**参数分发规则**、返回值 | 写命令必读 |
| [AI 工具](ai-tools.md) | `@ai_tools`、工具调用链 | 想让 AI 会干活 |
| [权限 RBAC](rbac.md) | 角色、`require_role` / `require_role_async` | 写命令必读 |
| [上下文 context](context.md) | 当前会话信息怎么拿 | 写命令必读 |
| [主动推送 push](push.md) | 后台任务怎么发消息 | 写后台任务必读 |
| [配置](config.md) | `config.yaml` / `.env` / `modules.json` | 部署 |
| [会话历史](history.md) | `HistoryManager`、文件布局 | 需要读写的 |
| [常见陷阱](pitfalls.md) | 踩过的坑，**建议通读** | 所有人 |
| [运维与排障](ops.md) | `run.sh`、日志、NapCat | 部署 |

## 5 分钟上手

### 1. 目录结构

```
AullBot/
├── src/aullbot/
│   ├── main.py              入口：事件监听 + 命令分发
│   ├── module_manager.py    模块系统（mm）
│   ├── module_meta.py       ModuleMeta 定义
│   ├── command_registry.py  @command / @ai_tools
│   ├── rbac.py              权限
│   ├── context.py           当前会话上下文
│   ├── push.py              主动推送
│   ├── chat.py              AI 会话主循环
│   ├── history_utils.py     历史/配置读写
│   ├── user_utils/          /manager 等
│   └── tools/               ← 所有业务模块都放这里
├── bot_data/                运行时数据（群/私聊配置、历史、订阅）
├── scripts/run.sh           启动脚本（可选）
├── scripts/init_env.py      交互式初始化 .env（密钥/QQ/B站凭据）
├── scripts/init_data.py     交互式初始化 bot_data（提示词/模板）
├── scripts/bili_login.py    单独扫码登录 B站
├── scripts/env_utils.py     .env 读写与提问工具
├── config.yaml              bot 全局配置（QQ 号、适配器）
├── .env                     密钥（B站 cookie、LLM key 等）
└── .aullver                 版本号
```

### 2. 写第一个模块

```python
# src/aullbot/tools/hello.py
from aullbot.module_meta import ModuleMeta
from aullbot.command_registry import command
from aullbot.rbac import require_role

MODULE = ModuleMeta(          # ← 必须有，否则命令注册会被拒绝
    name="hello",
    author="you",
    description="示例模块",
    version="1.0.0",
    default_enabled=True,
    tags=("demo",),
)

@command("/hello")
@require_role("user")
def hello(text: str = "") -> str:
    """打个招呼"""
    return f"你好，{text or '世界'}"
```

放好后重启，群里发 `/hello` 就能用。

### 3. 初始化环境变量

```bash
python scripts/init_env.py      # 一次问完：DeepSeek key / QQ 号 / B站扫码
```

### 4. 初始化数据（首次必须）

`bot_data/` 不进仓库，克隆后是空的：

```bash
python scripts/init_data.py
```

想用自己的系统提示词，先写 `scripts/assets/system_prompt.md` 再跑。

### 5. 启动（手动，推荐）

```bash
uv run python -u -m aullbot.main
```

**NapCat 和 `config.yaml` 不用你管**——`skip_setup` 默认 `false`，
ncatbot 会在首次启动时自动下载/配置/启动 NapCat 并等你扫码登录。

后台常驻自己挂 session：

```bash
screen -S aullbot
uv run python -u -m aullbot.main      # Ctrl+A D 脱离
```

> `scripts/run.sh` 是**可选封装**，只在"机器上已有 NapCat、且 `skip_setup: true`"时使用。
> 全新机器不需要它，直接用上面的 `uv run` 就行。

### 6. 常用内置命令

| 命令 | 作用 |
|---|---|
| `/help` | 列出所有命令 |
| `/module list` | 列出模块与状态 |
| `/module disable <name>` | 热禁用模块 |
| `#aull` | bot 状态（版本/平台/运行时长） |

## 设计原则

1. **一切皆模块**：命令、AI 工具、后台任务都挂在 `ModuleMeta` 下，可整体开关
2. **命令优先于 AI**：消息先过命令路由，不匹配才可能进 AI
3. **失败不致命**：后台任务永不因单次异常退出，推送失败只在调用方处理
4. **最小惊讶**：参数按 shell 规则切分，长度、超时、上限都有兜底

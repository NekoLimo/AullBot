# AullBot

基于 [ncatbot](https://github.com/ncatbot/ncatbot) 的 QQ 机器人：**模块化、可热插拔、命令与 AI 工具双路由**。

```
QQ ↔ NapCat（OneBot 11 / WebSocket）↔ ncatbot ↔ AullBot 框架 ↔ 模块
```

仓库：[NekoLimo/AullBot](https://github.com/NekoLimo/AullBot)
当前版本：`Version Alpha 0.2.5 - 20261101`

---

## 特性

- **模块系统**：每个功能是一个模块，`/module enable|disable` 热开关，后台任务随之启停
- **命令 + AI 工具双路由**：命令优先，未命中才可能进 AI；同一函数可同时注册两种入口
- **权限分层**：全局 `root`（影响整个进程）/ 会话 `admin`（只作用于本群或本私聊）/ `user`
- **主动推送**：`aullbot.push` 统一封装后台任务发消息，永不抛异常，失败返回 `False`
- **原子写**：历史与配置用 `mkstemp + fsync + os.replace`，崩溃不会写坏文件
- **B站监控**：动态为主、投稿兜底，id + 时间水位线双条件去重，45 秒级推送
- **文档齐全**：[`docs/`](docs/) 下有 12 篇，含架构、模块、命令、权限、推送、踩坑清单

---

## 快速开始

### 1. 环境

- Python 3.13（见 `.python-version`）
- [uv](https://github.com/astral-sh/uv)
```bash
git clone https://github.com/NekoLimo/AullBot.git
cd AullBot
uv sync
```

### 2. 初始化环境变量

```bash
python scripts/init_env.py
```

依次询问 `LLM_API_KEY`（DeepSeek 密钥）、`QQ_NUMBER`（bot 自己的 QQ），
并可选择直接扫码登录 B站写入 `BILI_*` 凭据。

也可以手动写 `.env`：

```bash
export LLM_API_KEY="sk-..."
export QQ_NUMBER="100000001"
```

### 3. 初始化数据目录

```bash
python scripts/init_data.py
```

`bot_data/` 不进仓库，首次必须初始化。系统提示词有三种来源：

| 来源 | 说明 |
|---|---|
| 指定文件路径 | 已有 `.md` / `.txt` 提示词 |
| 生成空模板 | 建 `scripts/assets/system_prompt.md`，**填完再跑一次** |
| 最小默认 | `You are a helpful assistant.` |

### 4. 启动

```bash
uv run python -u -m aullbot.main
```

**NapCat 不用手动准备**：`config.yaml` 的 `skip_setup` 默认 `false`，
ncatbot 会在首次启动时自动下载、配置、启动 NapCat，并等你扫码登录 QQ。

后台常驻：

```bash
screen -S aullbot
uv run python -u -m aullbot.main      # Ctrl+A D 脱离
```

---

## 目录结构

```
AullBot/
├── src/aullbot/
│   ├── main.py              事件入口、命令分发
│   ├── module_manager.py    模块系统（mm）
│   ├── module_meta.py       ModuleMeta
│   ├── command_registry.py  @command / @ai_tools
│   ├── rbac.py              权限（root / admin / user）
│   ├── context.py           当前会话上下文
│   ├── push.py              主动推送
│   ├── settings.py          运行时配置（读 .env）
│   ├── chat.py              AI 会话主循环
│   ├── history_utils.py     历史与配置读写
│   ├── user_utils/          /manager 等内置命令
│   └── tools/               ← 所有业务模块
├── scripts/
│   ├── init_env.py          交互式初始化 .env
│   ├── init_data.py         交互式初始化 bot_data
│   ├── bili_login.py        单独扫码登录 B站
│   ├── env_utils.py         .env 读写 + 提问工具
│   ├── run.sh               可选封装（已有 NapCat 时）
│   └── assets/              模板
├── docs/                    框架文档
├── tests/                   回归测试
├── bot_data/                运行时数据（不入库）
├── config.yaml              bot 全局配置（不入库）
└── .env                     密钥（不入库）
```

---

## 内置命令

| 命令 | 权限 | 说明 |
|---|---|---|
| `/say [延迟秒数] 内容` | user | 复读；延迟 > 0 时定时发送 |
| `/time` | user | 当前时间 |
| `/b64en` `/b64de` `/ascii_en` `/ascii_de` `/txt2bin` `/bin2txt` | user | 编解码 |
| `/vme50` `/vivo50` `/v50` | user | 玩梗 |
| `/img 内容` | user | 白底黑字图片 |
| `/music` `/search-music` `/download-music` `/send-music` `/list-cache` | user | 音乐 |
| `/震动` | user | 戳一戳 |
| `/bili-sub` `/bili-unsub` `/bili-list` | user | B站订阅 |
| `/bili-check` `/bili-sync` | admin | 检查本会话订阅 / 对齐基线 |
| `/module [list\|info\|enable\|disable\|sync]` | **root** | 模块热开关 |
| `#aull` | user | bot 状态（版本/平台/架构/运行时长） |
| `/manager <子命令>`（别名 `/mg`） | 见下 | 会话管理 |

`/manager` 子命令：

| 子命令 | 权限 | 说明 |
|---|---|---|
| `help` | user | 列出子命令 |
| `whoami` | ALL | 显示自己在当前会话的角色 |
| `get-config` | user | 查看本会话配置 |
| `clear` | admin | 清空本会话 AI 历史 |
| `set-prompt` | admin | 设置本会话提示词 |
| `add-admin` / `remove-admin` | admin | 增删会话管理员 |
| `ban` / `unban` | admin | 拉黑 / 解封（只接受纯数字 QQ，`root` 不可被封禁） |

---

## 写一个模块

```python
# src/aullbot/tools/hello.py
from aullbot.module_meta import ModuleMeta
from aullbot.command_registry import command
from aullbot.rbac import require_role

MODULE = ModuleMeta(           # 必须有，否则整个文件被跳过
    name="hello",
    description="示例模块",
    version="1.0.0",
)

@command("/hello")
@require_role("user")
def hello(text: str = "") -> str:
    """打个招呼"""
    return f"你好，{text or '世界'}"
```

要点：

- 文件必须放 `src/aullbot/tools/`，且顶层声明 `MODULE`
- 命令用 `@require_role`（同步）或 `@require_role_async`（异步），**别写反**
- 后台任务写在 `register(bot)` 的 `mod.on_load` 里，用 `m.spawn(...)`
- 循环里必须 `except asyncio.CancelledError: raise`，否则禁用后取消不掉
- **只改 `tools/` 下的文件**，框架层由维护者负责，详见 [边界](docs/boundaries.md)

---

## 配置

| 文件 | 内容 | 是否入库 |
|---|---|---|
| `.env` | 密钥、QQ 号、B站凭据、模型参数 | ❌ |
| `config.yaml` | NapCat 适配器、root QQ、debug | ❌ |
| `bot_data/modules.json` | 模块开关与模块配置 | ❌ |
| `bot_data/root.json` | 全局 root 列表 | ❌ |
| `bot_data/<group\|private>/<id>/config.json` | 会话权限与提示词 | ❌ |

模型参数全部可用环境变量覆盖：

```bash
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-...
LLM_EFFORT=high            # low | high | max
LLM_THINKING=disabled      # enabled | disabled
LLM_MAX_TOOL_ITERATIONS=5
```

优先级：**真实环境变量 > `.env` > 代码默认值**。详见 [配置文档](docs/config.md)。

---

## 测试与检查

```bash
./.venv/bin/python tests/test_bilibili_monitor.py   # 98 条断言，不联网
./.venv/bin/ruff check src scripts                   # 静态检查
```

`tests/` 里的其它文件是早期草稿，未纳入回归。

---

## 文档

| 文档 | 内容 |
|---|---|
| [边界](docs/boundaries.md) | 框架 vs 模块，谁能改什么 |
| [架构](docs/architecture.md) | 分层、消息流、启动流程、导入耗时拆解 |
| [模块系统](docs/module-system.md) | `ModuleMeta` / 热开关 / 生命周期 |
| [命令](docs/commands.md) | 参数分发规则（含 `get_raw_message()` 自救） |
| [AI 工具](docs/ai-tools.md) | 工具注册与调用链 |
| [权限](docs/rbac.md) | root / admin / 会话配置 |
| [上下文](docs/context.md) | 当前会话信息 |
| [推送](docs/push.md) | 后台任务怎么发消息 |
| [配置](docs/config.md) | 四层配置说明 |
| [历史](docs/history.md) | 磁盘布局与原子写 |
| [踩坑](docs/pitfalls.md) | 15 个真实问题，建议通读 |
| [运维](docs/ops.md) | 手动启动、扫码登录、排障 |

---

## 已知限制

- 私聊一律按会话最高权限（`admin`）处理；全局能力只认 `root`
- 会话配置里不再有 `rbac.list.root`，root 只来自 `bot_data/root.json` 或 `AULLBOT_ROOT`
- AI 历史无上限，长会话可能撞上下文限制
- 未在 Windows 下做过测试回归（脚本与运维依赖 bash / screen、`/dev/tcp`）

---

## 上游与依赖

AullBot 站在这些项目之上：

| 项目 | 作用 | 说明 |
|---|---|---|
| [ncatbot](https://github.com/ncatbot/ncatbot) | QQ 协议接入（OneBot 11 / WebSocket）、事件分发、NapCat 托管 | **核心上游**。AullBot 的模块系统、命令路由、权限、推送都是在其之上自建的 |
| [NapCatQQ](https://github.com/NapNeko/NapCatQQ) | 无头 QQ 客户端 | `skip_setup: false` 时由 ncatbot 自动下载安装 |
| [bpi-py](https://github.com/Yuelioi/bpi-py) | B站 API 客户端 | `bilibili_monitor` 用；走 `/x/polymer/web-dynamic/v1/feed/space` |
| [openai-python](https://github.com/openai/openai-python) | LLM 调用 | 兼容 DeepSeek 等 OpenAI 协议端点 |
| Pillow | 图片渲染 | `/img` 生成白底黑字图 |

本仓库**不含**这些项目的源码，通过 `pyproject.toml` 声明依赖。
各上游的许可与版本要求以其官方仓库为准；字体另见下节与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

> 与上游的关系：AullBot 不是 ncatbot 的 fork，也不修改其源码。
> 升级 ncatbot 时可能出现接口变动（例如 `BotAPIClient` 的 `_platforms`、
> `Forward`/`ForwardNode` 类型），这类兼容问题需在框架层适配。

---

## 第三方字体许可

`img.py` 直接使用 `fonts/` 下的两份 OFL 字体：

- `fonts/JetBrainsMonoNerdFont-Regular-v1.2.ttf` — JetBrains Mono 2.304 + Nerd Fonts 3.2.1，SIL OFL 1.1；
- `fonts/SourceHanSansCN-Regular.otf` — Source Han Sans CN 2.005，SIL OFL 1.1（RFN `Source`）。

`AULLBOT_IMG_FONT=auto|mono|sans` 可切换渲染字体（默认 `auto`）。
详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [LICENSES/](LICENSES/)。

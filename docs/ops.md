# 运维与排障

## 1. 手动启动（推荐）

**不推荐用 `run.sh` 起步。** 直接用 Python 启动，NapCat 交给 ncatbot 自己配。

### 1.1 装依赖

```bash
cd /root/AullBot
uv sync                       # 或 ./.venv/bin/pip install -e .
```

要求 Python 3.13（见 `.python-version`）。

### 1.2 初始化 `.env`

统一走 `init_env.py`，把**所有环境变量**一次问完：

```bash
python scripts/init_env.py          # 交互式
python scripts/init_env.py --yes    # 全取默认（不提问、不扫码）
```

| 变量 | 说明 |
|---|---|
| `LLM_API_KEY` | LLM 密钥（输入不回显） |
| `QQ_NUMBER` | bot 自己的 QQ 号 |
| `BILI_*` | B站凭据；选"现在扫码"会直接进扫码流程，不用另开脚本 |

已存在的值打码显示，回车保留原值：

```
当前 /root/AullBot/.env：
  LLM_API_KEY          abcd...wxyz
  QQ_NUMBER            100000001
  BILI_SESSDATA        （空）
```

写入前再确认一次，完成后备份 `.env.bak`、权限 600。

> 只想单独换 B站 cookie 时，仍可用 `scripts/bili_login.py`。

### 1.3 初始化 bot_data（首次必须）

`bot_data/` 不进仓库（`.gitignore` 里），所以克隆下来是空的，得先初始化：

```bash
python scripts/init_data.py        # 交互式
python scripts/init_data.py --yes  # 全取默认（脚本/CI 用）
```

交互流程：

```
1. 检测已有数据 → 保留 / 重建 / 退出
2. 选系统提示词来源
3. 显示将要做的事 → 确认
```

**系统提示词不在终端里手打**（容易漏行、被误判），只接受三种来源：

| 选项 | 行为 |
|---|---|
| 用 `scripts/assets/system_prompt.md` | 该文件存在且非空时才出现 |
| 指定其它文件路径 | 输入 `.md` / `.txt` 路径；读不到会提示并回退默认 |
| 生成空模板 | 建空的 `system_prompt.md`，**你填完再跑一次** |
| 最小默认 | `You are a helpful assistant.` |

生成模板分支不会写 `bot_data/`，填好再跑一次即可：

```
✅ 已生成空模板: scripts/assets/system_prompt.md
   编辑它，把你的提示词写进去，然后重新运行:
     python scripts/init_data.py
```

它会建：

```
bot_data/
├── group/group_list.json       []
├── private/private_list.json   []
├── system_prompt.json          ← 从 scripts/assets/system_prompt.md 生成
├── system_prompt.md
└── template_config.json        ← 从 scripts/assets 复制
```

**仓库不带人格提示词**，想用自己的就把内容写进
`scripts/assets/system_prompt.md` 再跑（没有则用 `You are a helpful assistant.`）。

已有数据时会拒绝覆盖：

```
❌ bot_data 里已有 N 个群的数据，拒绝覆盖。
   确实要重建请加 --force（会清空 group_list / private_list，但不动各群目录）
```

### 1.3.1 直接启动

```bash
uv run python -u -m aullbot.main
```

`-u` 关掉输出缓冲，日志立刻可见。

### 1.4 首次启动会发生什么

`config.yaml` 里 `skip_setup` 默认 `false`，所以 **ncatbot 自己搞定 NapCat**：

```
1. 探测 ws_uri 上的服务是否已在跑
   ├─ 在跑 → 直接复用，跳过下面全部
   └─ 不在 → 继续
2. 检查 NapCat 是否安装，缺了从 GitHub Releases 下载 NapCat.Shell 并解压
3. 生成 / 补全 NapCat 配置
4. 启动 QQ（无头，内部用 xvfb）
5. 等 WebUI 登录（首次扫码）
6. 连上 WebSocket，Bot 开始工作
```

**NapCat 和 `config.yaml` 都不用手动准备**，第一次跑起来它会自己写。

批量部署时可免掉安装确认：

```bash
export NCATBOT_SKIP_NAPCAT_INSTALL_CONFIRM=1
```

### 1.5 后台常驻

不占终端，自己挂 session（不需要 `run.sh`）：

```bash
screen -S aullbot
uv run python -u -m aullbot.main
# Ctrl+A D 脱离；回来 screen -r aullbot
```

或者：

```bash
nohup uv run python -u -m aullbot.main >> logs/bot_run.log 2>&1 &
```

### 1.6 停止

前台 `Ctrl+C`；后台 `pkill -f aullbot.main`。

---

## 2. B站扫码登录

`scripts/bili_login.py` —— 扫码拿 cookie 并自动写入 `.env`：

```bash
./.venv/bin/python scripts/bili_login.py            # 交互式扫码登录
./.venv/bin/python scripts/bili_login.py --check    # 只校验现有凭据
./.venv/bin/python scripts/bili_login.py --dry-run  # 只生成二维码，不轮询
./.venv/bin/python scripts/bili_login.py --no-save  # 登录但不写文件
./.venv/bin/python scripts/bili_login.py --yes      # 全部取默认，不提问
```

交互点：

```
.env 里已有 6 项 B站凭据：
  BILI_SESSDATA     abcd...wxyz        ← 打码显示
要重新扫码覆盖吗？ [Y/n]

（扫码成功后）
写入 .env 的字段：
  BILI_SESSDATA     abcd...wxyz
写入 .env？ [Y/n]
```

`.env` 的读写走公共模块 `scripts/env_utils.py`（备份、600 权限、保留其它变量）。

流程：

1. 生成二维码（终端直接显示 + 存 `qr.png`）
2. 轮询：`86101` 等待扫码 → `86090` 已扫码待确认 → `0` 成功 / `86038` 失效
3. 从返回 URL / `Set-Cookie` 取 `SESSDATA`/`bili_jct`/`DedeUserID`/`buvid3`/`buvid4`/`ac_time_value`
4. 用 `nav` 接口验证，打印昵称和 UID
5. 写 `.env`：**保留其它变量**、备份为 `.env.bak`、权限 600

`--check` 输出：

```
读取 /root/AullBot/.env
isLogin=True uname=示例用户 mid=1234567890 code=0
```

> `isLogin=False` + `code=-101` 不一定是过期，可能是被风控降级成匿名，过会儿再试。

---

## 3. 可选：`run.sh` 封装

只在**机器上已有 NapCat**、并且 `config.yaml` 配了 `skip_setup: true` 时才有意义：

```yaml
adapters:
- type: napcat
  platform: qq
  config:
    ws_uri: ws://127.0.0.1:3001
    skip_setup: true
```

```bash
./scripts/run.sh start      # 启动 NapCat（若没起）+ Bot
./scripts/run.sh status     # 进程 / 端口 / 运行时长
./scripts/run.sh check      # 环境自检（依赖 + 端口 + 目录）
./scripts/run.sh logs 100   # 跟踪日志
./scripts/run.sh test       # 跑回归测试
./scripts/run.sh stop-all   # 全停
```

`run.sh` 会读 `skip_setup`：

- `true` → 由脚本管理 NapCat（会检查端口，识别"进程在但服务死了"）
- `false` → **不碰 NapCat**，只启动 Bot，避免和 ncatbot 抢同一个进程

```
ℹ️  模式:      本脚本托管 NapCat（skip_setup=true）
ℹ️  模式:      ncatbot 托管 NapCat（skip_setup=false）
```

### 换机器能用吗

不一定，没有硬编码路径了，靠"可覆盖 + 自动探测"：

| 变量 | 默认行为 |
|---|---|
| `NAPCAST_DIR` | 探测 `项目/Napcat`、`~/Napcat`、`/root/Napcat`、`/opt/Napcat` |
| `NAPCAST_PORT` | 从 `config.yaml` 的 `ws_uri` 解析，兜底 3001 |
| `NAPCAST_SESSION` / `BOT_SESSION` | `napcat` / `aullbot` |

| 项 | 逻辑 |
|---|---|
| 项目路径 | 从脚本位置推导 |
| Python | `.venv/bin/python` → `uv run python` → `python3` |
| shebang | `#!/usr/bin/env bash` |

依赖体检：

```bash
./scripts/run.sh check
```

会逐个检查 `bash screen pgrep pkill timeout tee`、`uv`、NapCat 目录、`xvfb-run`。

> `xvfb-run` 是 **NapCat（无头 QQ）的依赖**，不是 aullbot 决定的。
> 启动命令固定为 `xvfb-run -a <napcat>/opt/QQ/qq --no-sandbox -q $QQ_NUMBER`。

不支持：Windows（无 bash/screen）、无 `screen` 的精简容器（可用 `dev` 前台 + tmux）。

---

## 4. 登录掉线怎么恢复

现象：**QQ 进程还活着，但 3001 没监听**（掉线重登后 NapCat 没接管）。

```
NapCatLauncher ➜ 测试 WebSocket 连接失败: [Errno 111] Connect call failed
NcatBotError: 无法连接 NapCat WebSocket (ws://127.0.0.1:3001)
```

恢复步骤：

1. 打开 NapCat WebUI（默认 `http://127.0.0.1:6099/webui/`，以你的配置为准）
2. 输入 Token（在 NapCat 启动日志里，见 NapCat 文档）
3. 用手机扫码重新登录 QQ
4. 重新启动 Bot：

```bash
uv run python -u -m aullbot.main
# 或（skip_setup: true 时）
./scripts/run.sh stop-all && ./scripts/run.sh start
```

检查端口：

```bash
(echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null && echo OK || echo "NapCat 挂了"
```

---

## 5. 日志

```bash
tail -f logs/bot_run.log                      # 实时（run.sh 才写这个文件）
grep -a "\[bili\]" logs/bot_run.log | tail    # 只看监控
grep -a "Traceback" -A 15 logs/bot_run.log    # 看异常
```

手动启动时日志直接打在终端；要留存就用重定向或 `tee`。

常见日志行：

| 日志 | 含义 |
|---|---|
| `[main] 启动完成，初始化模块后台任务` | 模块开始 load |
| `[bili] 后台任务已注册` | 模块 register 成功 |
| `[bili] 监控已启动（bpi-py）` | 后台循环跑起来 |
| `[bili] 建立基线：动态 N 条、投稿 M 条` | 首次订阅，记基线不推送 |
| `[bili] 校准时间水位线` | 老状态升级，一次性校准 |
| `[bili] 推送 N 个会话` | 推送成功 |
| `[push] 未绑定 bot，发送失败` | `push.bind()` 没执行 |
| `[ModuleManager] Failed to load module` | 模块 on_load 抛异常 |

---

## 6. 健康检查

| 方式 | 说明 |
|---|---|
| `#aull` 命令 | 版本 / 平台 / 系统和架构 / 运行时长 |
| `/bili-check` | 立刻检查本会话订阅，返回成功/失败数 |
| `ps -eo pid,etime,args \| grep aullbot.main` | 看进程与运行时长 |
| `(echo > /dev/tcp/127.0.0.1/3001)` | 看 NapCat 端口 |

---

## 7. 升级流程

```bash
git pull
uv sync                          # 依赖有变时
# 手动启动的：Ctrl+C 后重新 uv run python -u -m aullbot.main
# run.sh 的：./scripts/run.sh restart-bot
```

---

## 8. 排障速查

| 现象 | 排查 |
|---|---|
| bot 不响应任何命令 | NapCat 在跑吗？3001 通吗？进程在吗 |
| 只有部分命令失效 | `/module list` 看模块是否被禁用 |
| 提示"未成功加载" | 该模块 import 失败，看启动日志 `[tools]` |
| 命令提示参数错误 | 参数个数不匹配，见 [commands.md](commands.md) |
| 推送收不到 | `/bili-list` 有订阅吗；`/bili-check` 成功吗 |
| 推送了历史内容 | `/bili-sync` 对齐基线 |
| 启动即退出（exit 1） | NapCat 连不上，按第 4 节重新登录 |
| 启动很慢（10s+） | 正常，`openai` + `bpi` 等重依赖导入 |
| 首次启动卡在下载 | 访问 GitHub Releases 慢，配代理或手动装 NapCat |

---

## 9. 数据备份

只需要备份 `bot_data/`：

```bash
tar czf bot_data-$(date +%F).tar.gz bot_data/
```

`.env` 单独保管（含密钥）。

| 文件 | 能不能丢 |
|---|---|
| `group/`、`private/` | 丢了会丢历史与群配置 |
| `modules.json` | 丢了回到默认开关 |
| `root.json` | 丢了 `/module` 没人能用（需重建） |
| `template_config.json` | **不能丢**，否则新群建不起来 |
| `system_prompt.json` | 不能丢（会退化成默认提示词） |
| `bilibili_state.json` | 丢了会重新建基线（不推历史，安全） |
| `bilibili_subs.json` | 丢了等于全部退订 |

# 配置

配置文件分四层，职责不重叠。

## 1. `.env` — 密钥

放在项目根，`scripts/run.sh` 启动时会 `source` 它。**不要提交到 git**。

```bash
export LLM_API_KEY=sk-xxx
export FLAG=xxx
export QQ_NUMBER=xxx

# B站（扫码登录写入）
export BILI_SESSDATA=xxx
export BILI_JCT=xxx
export BILI_DEDEUSERID=xxx
export BILI_BUVID3=xxx
export BILI_BUVID4=xxx
export BILI_AC_TIME_VALUE=xxx
```

| 变量 | 用途 |
|---|---|
| `LLM_API_KEY` | LLM 密钥，缺失时报 `Missing credentials` |
| `QQ_NUMBER` | bot 的 QQ 号 |
| `BILI_*` | B站 cookie，`bilibili_monitor` 用 |

## 1.5 模型配置（`.env`）

`src/aullbot/settings.py` 把所有模型参数改成环境变量，不用改代码：

```bash
# 模型
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-...
LLM_EFFORT=high                 # low | high | max
LLM_THINKING=disabled           # enabled | disabled
LLM_MAX_TOOL_ITERATIONS=5       # 工具调用最大轮数，1~20
```

优先级：**真实环境变量 > `.env` > 代码默认值**。

`.env` 由 `settings.load_dotenv()` 在启动时读取（不依赖 python-dotenv，也不覆盖已有变量），
所以手动 `uv run python -u -m aullbot.main` 也会生效，不必先 `source .env`。

非法值会回退默认并打印一次警告：

```
[settings] LLM_EFFORT='huge' 不在 ('low', 'high', 'max') 里，回退 high
[settings] LLM_MAX_TOOL_ITERATIONS='abc' 不是整数，回退 5
```

启动时 `chat.py` 会打印当前生效值：

```
[chat] model=deepseek-v4-pro base_url=https://api.deepseek.com key=已设置 effort=high thinking=disabled max_tool_iterations=5
```

## 2. `config.yaml` — bot 全局配置

由 NcatBot 框架生成，请按照 NcatBot 文档配置

## 3. `bot_data/modules.json` — 模块开关与配置

```json
{
  "bilibili_monitor": {
    "enabled": true,
    "config": {
      "interval": 45,
      "video_every": 1
    }
  }
}
```

- 只有被 `/module` 开关过、或手写过的模块才在这里
- 没出现的模块用代码里 `config_schema` 的默认值
- **改完要重启**（启动时读一次）

## 3.5 `bot_data/root.json` — 全局管理员

```json
{ "root": ["100000002"] }
```

`root` 拥有**全局**权限（如 `/module enable|disable`）。

优先级：`AULLBOT_ROOT` 环境变量 > 本文件 > ncatbot 的 `config.yaml`（兜底）。

> `config.yaml` 由 ncatbot 维护，aullbot 不把它当作必需依赖。

## 4. `bot_data/{group,private}/<id>/config.json` — 会话配置

```json
{
  "blacklist": [],
  "rbac": { "list": { "admin": ["$GROUP_OWNER"], "user": [] } },
  "prompt": [{"role": "system", "content": "你是群助理"}]
}
```

首次见到会话时由 `template_config.json` 复制生成。

## 5. 优先级

同名配置的读取顺序（以模块配置为例）：

```
代码里的 default  ←  modules.json 的 config  ←  运行时 /module 修改
      （兜底）            （覆盖）                  （写回 json）
```

## 6. 模板文件

| 文件 | 作用 |
|---|---|
| `bot_data/template_config.json` | 新会话配置模板，**缺了会导致新群建不起来** |
| `bot_data/system_prompt.json` | 全局 AI 系统提示词，会话没配 `prompt` 时使用 |
| `bot_data/group_list.json` | 已知群列表 |

## 7. 环境变量 vs 配置文件

| 放哪 | 什么 |
|---|---|
| `.env` | 密钥、cookie、token（可能变、不能提交） |
| `config.yaml` | 连接参数、身份（很少变） |
| `modules.json` | 功能开关与调参（会经常改） |
| `config.json`（会话） | 每群差异（权限、提示词） |

## 8. 常见问题

**Q: 改了 `modules.json` 没生效**
启动时读一次，需要重启。

**Q: 改了会话 `config.json` 没生效**
RBAC 有 60 秒缓存，等一会儿或重启。

**Q: `.env` 改了没生效**
`run.sh` 在启动时 source，需要重启进程。

**Q: `bot_uin` 和 `QQ_NUMBER` 不一致会怎样**
可能导致 `@机器人` 判断失效（`is_group_me` 用 `event.self_id`），建议保持一致。

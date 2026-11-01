# 架构总览

## 1. 分层

```
┌─────────────────────────────────────────────┐
│  QQ 客户端 ←→ NapCat（OneBot 11 / WebSocket）│  外部
└───────────────────┬─────────────────────────┘
                    │ ws://127.0.0.1:3001
┌───────────────────▼─────────────────────────┐
│  ncatbot（BotClient / registrar / api.qq）   │  第三方
└───────────────────┬─────────────────────────┘
┌───────────────────▼─────────────────────────┐
│  AullBot 框架层                              │
│    main.py          事件 → 命令分发          │
│    module_manager   模块注册 / 热开关        │
│    command_registry 命令与 AI 工具注册       │
│    rbac / context / push / history           │
└───────────────────┬─────────────────────────┘
┌───────────────────▼─────────────────────────┐
│  tools/*.py  业务模块（命令 + 工具 + 任务）   │
└─────────────────────────────────────────────┘
```

## 2. 一条群消息的完整流程

```
群消息到达
  │
  ├─ is_group_me(event)                      main.py
  │    1. 首次见到该群 → add_chat_list() 建目录和配置
  │    2. 把消息段拼成纯文本（忽略图片等非文本段）
  │    3. 去掉首尾的 @机器人
  │    4. context.set_context(...)            设置本次请求上下文
  │
  ├─ msg_text == "撤回" ？ → 撤回上一条，return
  │
  ├─ find_command(msg_text)                  main.py:59
  │    1. shlex.split 切词
  │    2. 命中命令表？
  │        ├─ 检查所属模块是否启用（/module 例外）
  │        ├─ 按参数个数分发调用
  │        └─ 返回字符串 → 直接回复，return
  │    3. 未命中 → 返回 -255（COMMAND_NOT_FOUND）
  │
  └─ 消息里有 @机器人 且未被命令处理？
       → ai_chat_main(...)                    chat.py
            → 组装 messages（系统提示词 + 历史）
            → 调 DeepSeek（带 tools 规格）
            → 模型要求调工具 → 执行 @ai_tools 函数 → 回灌结果
            → 最终文本 → 回复
```

私聊流程类似，区别：无 @ 判断、`user_role` 直接给 `"owner"`。

## 3. 启动流程

```
python -m aullbot.main
  │
  ├─ import 阶段（约 5~25 秒）
  │    from aullbot.tools import command_route
  │      → 扫描 tools/*.py
  │      → AST 预检查每个文件是否声明 MODULE（没声明就跳过并告警）
  │      → importlib 加载 → @command/@ai_tools 注册到全局表
  │      → 收集模块的 register(bot) 到 _pending_registers
  │
  ├─ bot = BotClient()                       读 config.yaml 建适配器
  │
  ├─ @bot.on_startup()  _on_startup()
  │    └─ _lazy_start()
  │         ├─ push.bind(bot)                绑定主动推送
  │         ├─ 逐个调用 _pending_registers   模块注册后台任务
  │         └─ mm.load_all(bot)              触发各模块 on_load
  │
  └─ bot.run()                               开始收消息
```

## 4. 三条发送通道

| 通道 | 场景 | 写法 |
|---|---|---|
| 返回值 | 命令处理完返回字符串 | `return "文本"`，框架自动发给当前会话 |
| `event.reply` | 有事件对象时 | 目前框架内用得少 |
| `aullbot.push` | **没有**当前会话上下文（后台/定时） | `await push.send_group(...)` |

详见 [命令](commands.md) 与 [主动推送](push.md)。

## 5. 导入耗时（实测）

曾经启动要 10~25 秒，实测拆开看，**几乎全是 `openai` 一个包**：

| 模块 | 冷启动耗时 |
|---|---|
| `openai` | **5.8s**（热缓存约 3s） |
| `bpi` | 2.6s |
| `requests` | 0.9s |
| `PIL` | 0.03s |
| `ncatbot` | <0.1s |
| **`aullbot.tools` 整体** | **6.45s** |

### 找到的两个元凶

**① `history_utils.py` 为了一个 `isinstance` 拖进整个 openai**

```python
from openai.types.chat import ChatCompletionMessage    # ❌ 3~6 秒

if isinstance(content[0], (dict, ChatCompletionMessage)):
```

而 `rbac` → `history_utils` 这条链在启动早期就被引入，等于把 openai 拽进每一处。

改法：运行时用鸭子类型判断，只在类型检查时导入：

```python
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessage
else:
    ChatCompletionMessage = Any

def _is_sdk_message(obj) -> bool:
    return (not isinstance(obj, dict)
            and hasattr(obj, "role") and hasattr(obj, "content"))
```

**② `chat.py` 在模块顶层创建 OpenAI 客户端**

```python
client = OpenAI(api_key=..., base_url=...)    # ❌ import 时就建
```

改法：第一次真正调用再创建：

```python
_client = None
def get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(...)
    return _client
```

### 优化结果与取舍

| | 优化前 | history_utils 修完 | 最终 |
|---|---|---|---|
| `import aullbot.tools` | 6.45s | **2.92s** | 2.92s |
| `import aullbot.chat` | 5.8s+ | 2.73s | **10.2s** |
| 启动总导入 | 12.9~19.9s | 2.76s | **11.16s** |
| 第一条 AI 消息延迟 | 无 | **+5~7 秒** | 无 |

**最终选择：`chat.py` 的客户端保留在模块顶层创建。**

延迟创建虽然让启动快了 8 秒，但代价转嫁到了用户身上：

```
用户发第一条消息 → 触发 call_ai → import openai（5~7 秒）→ 才发出请求
```

用户看到的就是"机器人没反应"，比等启动更难受。所以：

```python
# chat.py 顶层
client = OpenAI(api_key=..., base_url=...)   # 启动时一次性付清
```

**但 `history_utils.py` 的鸭子类型改造保留**——那个是纯收益：
它把 openai 从 `rbac → context` 这条早期导入链上摘掉了，
其它不经过 `chat.py` 的入口（测试、脚本、单模块导入）都能少等 5~7 秒。

结论：
- **启动耗时**：愿意付（没人盯着）
- **首条消息延迟**：不能付（用户会以为卡了）

剩余 2.9s 主要是 `bpi`(2.6s) 与 `requests`(0.9s)。`bpi` 已在 `bilibili_monitor`
里做成函数内延迟导入，但它在 `-X importtime` 里仍会出现于首次调用时。

# 上下文（context）

## 1. 是什么

每条消息处理前，`main.py` 会把「这次请求需要的全局依赖」塞进 `ContextVar`：

```python
@dataclass
class RequestContext:
    bot          # NcatBot BotClient，原生调用NcatBot API，全局单实例
    chat_type    # 0=群 1=私聊
    chat_id      # 群号 / QQ号
    cache_path   # 缓存目录
    user_role    # 发送者角色（群主/管理员/成员）
    sender_id    # 发送者 QQ 号
    raw_message  # 原始消息全文（保留换行）
```

## 2. 取值 API

```python
from aullbot import context

bot        = context.get_bot()
chat_type  = context.get_chat_type()      # 0 / 1
chat_id    = context.get_chat_id()        # int 或 str
cache_path = context.get_cache_path()
user_role  = context.get_user_role()      # "owner" / "admin" / "member" / None
sender_id  = context.get_sender_id()
raw        = context.get_raw_message()

ctx = context.get_context()               # 一次拿全部
```

没设置时 `get_context()` 抛 `RuntimeError("No context set...")`。

## 3. 什么时候有值

| 场景 | 有 context？ |
|---|---|
| 群/私聊消息处理期间 | ✅ |
| 命令函数里 | ✅ |
| AI 工具函数里 | ✅（仍在请求内） |
| `asyncio.create_task` 创建的任务里 | ✅（ContextVar 会复制到任务） |
| 后台轮询任务（`mod.spawn`） | ❌ |
| 定时任务到点时 | ⚠️ 取决于创建方式 |

**最后一条要注意**：`asyncio.create_task` 会复制当前 ContextVar，
所以定时任务里 `get_chat_id()` 可能"碰巧"还能用。但这是**隐式依赖**，重启/重构就断。

**正确做法**：定时任务在创建时就把目标记下来，用 `push` 显式发送：

```python
async def delayed_send(seconds, chat_type, chat_id, text):
    await asyncio.sleep(seconds)
    await push.send(chat_type, chat_id, text)      # 显式目标

# 命令里
asyncio.create_task(delayed_send(30, context.get_chat_type(), context.get_chat_id(), text))
```

## 4. 用 context 还是 push

| 发送时机 | 用什么 |
|---|---|
| 就在这条消息的处理流程里 | 直接 `return` 字符串，或NcatBot API `bot.api.qq.post_group_msg` |
| 后台任务 / 定时 / 请求已结束 | `push` |

`push` 详见 [push.md](push.md)。

## 5. 常见用法

```python
# 判断群聊还是私聊
if context.get_chat_type() == 0:
    ...

# 只为群主开放
if context.get_user_role() not in ("owner", "admin"):
    return "仅管理员可用"

# 拿原始消息（含换行，命令解析会 strip）
raw = context.get_raw_message()
```

## 6. 陷阱

**① 别在模块导入期调用**

```python
# ❌ 导入时没有 context
CHAT_ID = context.get_chat_id()
```

**② 后台任务里不要直接调**

```python
async def _loop(bot):
    # ❌ 这里 context 是空的，或残留了某个用户的值
    await context.get_bot().api.qq.post_group_msg(...)
```

**③ ContextVar 复制不等于安全**

任务里能读到值是 asyncio 的复制行为，不是设计意图。一旦这个任务在别的请求里被创建，
读到的就是**那个请求**的会话，可能发错群。

# 主动推送接口（`aullbot.push`）

> 源码：[`src/aullbot/push.py`](../src/aullbot/push.py)

## 1. 它解决什么问题

命令和 AI 工具都在「某条用户消息」的上下文里，回复很方便。但有三类发送**没有这个上下文**：

- 后台轮询任务（如 B 站监控发现新动态）
- 定时任务（如 `/say 30 xxx`，30 秒后原请求早结束了）
- 跨模块通知（A 模块想告诉 B 模块的群）

这些场景不能依赖 `context` 或 `event.reply`，统一走 `aullbot.push`。

## 2. 什么时候**不**该用它

判断标准只有一条：**发送这一刻，还有没有「当前会话」上下文**。

| 场景 | 用 push？ | 理由 |
|---|---|---|
| 后台轮询/定时任务主动发 | ✅ 用 | 没有上下文 |
| 命令处理里回复用户 | ❌ 不用 | 直接用 `context.get_bot()` / `event.reply` |
| AI 工具里发消息 | ❌ 不用 | 仍在请求上下文里 |
| 事件回复（`main.py` 的 `post_group_msg`） | ❌ 不用 | 有 `event` |

> 这条边界很重要。如果把「回复」也接进 push，它会从「主动推送接口」退化成「发送工具函数」，
> 并给所有模块引入一个「必须先 bind」的隐式依赖。

## 3. 绑定

框架在启动时自动绑定，业务代码**不需要管**：

```python
# src/aullbot/main.py 的 _lazy_start()
push.bind(bot)
```

如果模块在 `register(bot)` 里自建后台任务，建议加一句兜底：

```python
if not push.is_bound():
    push.bind(bot)
```

未绑定时所有发送返回 `False`，并打印 `[push] 未绑定 bot，发送失败`。

## 4. 接口一览

所有接口都是 `async`，**永不抛异常**。

### 4.1 `send_group(group_id, text) -> bool`

向群发纯文本。

```python
await push.send_group(100000001, "服务器将于 10 分钟后重启")
```

### 4.2 `send_private(user_id, text) -> bool`

向私聊发纯文本。

```python
await push.send_private(100000002, "你的订阅已生效")
```

### 4.3 `send(chat_type, chat_id, text) -> bool`

按会话类型分发，`0`=群、`1`=私聊。适合类型来自变量的场景。

```python
await push.send(chat_type, chat_id, "内容")
```

### 4.4 `send_many(targets, text, gap=0.3) -> int`

批量广播，返回**成功条数**。`targets` 形如 `[("group", 群号), ("private", QQ号)]`。

- 自动去重（同一目标只发一次）、保序
- 两次发送之间隔 `gap` 秒（默认 0.3），避免触发风控

```python
targets = [("group", 111), ("group", 222), ("private", 333)]
ok = await push.send_many(targets, "【公告】今晚维护")
print(f"送达 {ok} 个会话")
```

### 4.5 `send_forward(chat_type, chat_id, blocks, nickname="通知", sender_id="0") -> bool`

合并转发（QQ 的「聊天记录」卡片），`blocks` 为 `[(标题, 正文), ...]`，每条一个节点。

适合内容长、会刷屏的场景。

```python
await push.send_forward(0, 100000001, [
    ("UP 1234567890123456", "动态 5 条 / 投稿 5 条\n……"),
    ("UP 1462632510", "动态 0 条 / 投稿 5 条\n……"),
], nickname="B站同步", sender_id=100000002)
```

| 参数 | 说明 |
|---|---|
| `blocks` | `[(标题, 正文)]`，空列表直接返回 `False` |
| `nickname` | 节点显示的昵称 |
| `sender_id` | 节点显示的 QQ 号（展示用，可传任意字符串） |

### 4.6 `send_record(chat_type, chat_id, file) -> bool`

发送语音，`file` 支持本地路径或 URL。

```python
await push.send_record(0, 100000001, "/tmp/tts.mp3")
```

### 4.7 辅助函数

| 函数 | 说明 |
|---|---|
| `bind(bot)` | 绑定 BotClient，启动时调用一次 |
| `is_bound() -> bool` | 是否已绑定 |

## 5. 返回值与错误处理

| 情况 | 行为 |
|---|---|
| 成功 | 返回 `True`（`send_many` 返回成功条数） |
| 未绑定 | 返回 `False`，打印 `[push] 未绑定 bot` |
| 群号/QQ号非法 | 返回 `False`，打印 `[push] 群号非法: 'abc'` |
| 发送异常（被禁言等） | 返回 `False`，打印 `[push] 群 123 发送失败: RuntimeError: ...` |

**永远不会抛异常**，所以调用方不用包 `try`，只需判断返回值：

```python
if not await push.send_group(gid, text):
    # 自己做重试 / 记录，框架不会替你做
    logger.warning("推送失败，稍后重试")
```

> 注意：`push` **不重试**。重试策略由调用方决定（例如 B 站监控是「推送失败就不推进状态，下一轮再推」）。

## 6. 完整示例

### 6.1 后台任务推送

```python
import asyncio
from aullbot import push


async def watch_loop(bot):
    while True:
        items = await fetch_new_items()
        if items:
            text = "\n".join(f"· {x['title']}" for x in items)
            ok = await push.send_many([("group", 100000001)], text)
            if not ok:
                print("[watch] 推送失败，本轮不推进状态")
        await asyncio.sleep(60)
```

### 6.2 定时发送

```python
async def delayed_send(delay: float, chat_type: int, chat_id, text: str):
    await asyncio.sleep(delay)
    await push.send(chat_type, chat_id, text)
```

（`/say 30 开会了` 就是这么实现的，见 [`basics.py`](../src/aullbot/tools/basics.py)）

### 6.3 长内容用合并转发

```python
blocks = [(f"UP {uid}", body) for uid, body in results]
if not await push.send_forward(chat_type, chat_id, blocks, nickname="B站同步"):
    # 合并转发失败，退回纯文本
    await push.send(chat_type, chat_id, "\n\n".join(f"{t}\n{b}" for t, b in blocks))
```

## 7. 实际使用方

| 位置 | 用途 |
|---|---|
| [`bilibili_monitor.py`](../src/aullbot/tools/bilibili_monitor.py) | 新动态/投稿推送、`/bili-sync` 合并转发 |
| [`basics.py`](../src/aullbot/tools/basics.py) | `/say` 定时发送 |
| [`main.py`](../src/aullbot/main.py) | 启动时 `push.bind(bot)` |

## 8. 设计取舍

**为什么用全局 `bind` 而不是每次传 `bot`？**

后台任务通常拿不到 `bot`（模块 `register(bot)` 能拿到，但定时任务里传一路很啰嗦）。
全局绑定一次，调用点干净。代价是「必须先绑定」，所以启动流程里必须调用 `push.bind(bot)`，
模块自建任务时建议加 `is_bound()` 兜底。

**为什么永不抛异常？**

推送发生在后台，异常会污染任务循环。返回 `False` 让调用方自己决定重试，语义更明确。

**为什么 `send_many` 要去重？**

订阅关系常常多路径汇聚（同一 UP 被多个群订阅），不去重会重复轰炸同一个会话。

## 9. 测试

`tests/test_bilibili_monitor.py` 的 `[21] 主动推送接口` 一节覆盖：

- 绑定前后行为
- 单发/按类型发送
- 批量去重与顺序
- 合并转发节点数
- 非法参数返回 `False`

运行：

```bash
./.venv/bin/python tests/test_bilibili_monitor.py
```

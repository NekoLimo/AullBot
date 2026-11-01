# 命令

## 1. 定义

```python
from aullbot.command_registry import command
from aullbot.rbac import require_role

@command("/ping")
@require_role("user")
def ping(text: str = "") -> str:
    """回复 pong"""
    return "pong"
```

装饰器顺序无所谓，但**必须**同时有 `@command` 和权限装饰器（否则任何人都能用）。

`@command` 做的事：

```python
command_registry[name] = func      # 全局命令表
mm.bind_command(owner, name)       # 记录归属模块
```

`owner` 从函数所在模块的 `MODULE` 推断；没有 `MODULE` 会拒绝注册并打印：

```
[command] mymodule.ping 未定义 MODULE，拒绝注册 /ping
```

## 2. 参数分发规则（最容易踩坑的地方）

`find_command` 按**函数参数个数**决定怎么传参：

```python
n = len(inspect.signature(func).parameters)
if n == 1:
    func("整个参数串")          # 剩余全部合成一个字符串
else:
    func(*tokens[1:][:n])      # 按空格切，只取前 n 个
```

### 单参数：整段进来

```python
@command("/say")
def say(text: str) -> str:
    return text

# /say 你好 世界      → text="你好 世界"     ✅ 含空格也能收到
# /say 你好
世界                  → text="你好 世界"    ❌ 吞换行
# /say 1 2 3         → text="1 2 3"
```

### 多参数：按空格切，且超出部分被丢弃

```python
@command("/toggle")
def toggle(name: str, enable: bool) -> str:
    ...

# /toggle bili true     → name="bili", enable="true"（字符串！）
# /toggle a b c d       → name="a", enable="b"      ❌ "c" "d" 被静默丢弃
```

**框架层确实只传前 n 个 token**，多出来的不会报错，直接消失。

### 但命令可以自救：`context.get_raw_message()`

框架在处理消息前把**完整原文**放进了上下文：

```python
context.get_raw_message()      # "/img a b c d"，含空格和换行
```

所以多参数命令如果内容需要空格，别用切片值，自己从原文里抠。`/img` 就是这么做的：

```python
@command("/img")
@require_role_async("user")
async def img(text: str, get_con: bool = True) -> str | None:
    if get_con:                                    # 命令调用走这里
        raw = context.get_raw_message()
        m = re.search(r'^/img\s?(.*)', raw, re.DOTALL)
        text = m.group(1)                          # 完整文本，空格换行都保留
    ...                                            # else: AI 工具调用，直接用参数
```

实测（图片宽度随文本长度增长）：

```
/img a                    → 图 148x146
/img a b c d              → 图 436x160     完整渲染 "a b c d"
/img 你好 世界 这是 很多 词   → 图 1012x177
```

> 这里的分发规则属于**框架层**。模块作者不要试图去改 `find_command`，
> 需要框架改进（比如给 `@command` 加 `raw_text=True`）请找维护者，见 [边界](boundaries.md)。

### 三种写法怎么选

| 场景 | 写法 |
|---|---|
| 内容可能含空格/换行 | **单参数**，框架自动整段传入 |
| 需要多个结构化参数（如 uid + 开关） | 多参数，但提醒用户加引号 |
| 既要多参数又要长文本 | 多参数 + `context.get_raw_message()` 自救（`/img` 模式） |

### 坑：布尔参数从命令行传永远是"真"

```python
def img(text: str, get_con: bool = True)
```

用户在群里发 `/img 猫 false`，`get_con` 拿到的是**字符串** `"false"`，
而 `bool("false") is True` —— 关不掉。

布尔参数只对**代码调用**（如 AI 工具）有意义；从消息里传必须自己解析：

```python
flag = str(get_con).lower() not in ("false", "0", "off", "")
```

## 3. 返回值

| 返回 | 行为 |
|---|---|
| 非空字符串 | 框架发给当前会话 |
| `None` / `""` | 什么都不发（适合已经自己发过消息的命令） |
| 其它类型 | 不发送（`main.py` 里 `isinstance(text_to_send, str)` 才发） |

自己发消息的命令（比如 `/bili-sync` 用合并转发）通常返回一句确认文字：

```python
await push.send_forward(...)
return "已发送，详情见上面的合并转发"
```

## 4. 异步命令

```python
@command("/slow")
@require_role_async("user")     # ← 异步必须用这个
async def slow(text: str = "") -> str:
    await asyncio.sleep(1)
    return "好了"
```

**`async def` 一定要配 `require_role_async`**。用同步版 `require_role` 会包出同步函数，
`inspect.iscoroutinefunction()` 返回 False，调用结果是一个没人 await 的协程对象，
表现为"命令有反应但不回复"。

框架已在 `find_command` 里加了兜底（拿到返回值后 `if inspect.isawaitable(ret): ret = await ret`），
但别依赖它——同步/异步配对写对才是正解。

## 5. 命令名

- 必须以 `/` 开头？**不需要**。路由表就是字符串精确匹配，`#aull`、`bili` 都能当命令名
- 但为了区分普通聊天，惯例用 `/` 或 `#`
- 中文命令名可行：`/状态`

## 6. 一个命令挂多个名字

```python
@command("/status")
@command("/状态")
@require_role("user")
def status() -> str:
    ...
```

也可以先定义再注册(不推荐)：

```python
def _impl() -> str: ...
command("/a")(_impl)
command("/b")(_impl)
```

## 7. 命令 vs AI 的分流

```
消息 → find_command
        ├─ 命中命令 → 执行 → return 字符串 → 回复
        └─ 未命中   → 返回 -255
              └─ 群里且 @了机器人 / 私聊 → 进 AI
```

所以命令**优先级高于 AI**，不会被模型"抢答"。

## 8. 排查

| 现象 | 原因 |
|---|---|
| 发命令没反应 | 模块被禁用（`/module list` 看）|
| 提示"未成功加载" | 该模块 import 失败了，看启动日志 `[tools]` |
| 提示"参数错误" | 参数个数不匹配（多参数命令没给够） |
| 返回 `<coroutine object ...>` | async 配了同步装饰器 |
| 命令名打错 | 大小写/拼写敏感，看 `/help` |

# AI 工具

## 1. 是什么

`@ai_tools` 注册的函数会被**大模型主动调用**。模型看到工具的名字、docstring 和参数，
自己决定什么时候调、传什么参数。

```python
from aullbot.command_registry import ai_tools
from aullbot.rbac import require_role_async

@ai_tools("bili_subscribe")
@require_role_async("user")
async def bili_subscribe(uid: str) -> str:
    """订阅 B站 UP 主更新，参数 uid 为数字 UID"""
    return await bili_sub(uid)
```

## 2. 注册与归属

```python
command_tools[name] = func     # 工具表
mm.bind_tool(owner, name)      # 记录归属模块
```

工具也受模块开关控制：模块禁用后，模型再调用会得到

```
工具 xxx 所属模块 bilibili_monitor 已被禁用，请勿再调用
```

（这段在 `chat.py` 里处理，见下。）

## 3. 规格生成

`tools/__init__.py` 的 `generate_ai_tools_spec()` 把注册表转成 OpenAI function-calling 格式：

```python
[
  {
    "type": "function",
    "function": {
        "name": "bili_subscribe",
        "description": "订阅 B站 UP 主更新，参数 uid 为数字 UID",   # ← docstring 第一段
        "parameters": {...}                                        # ← 由类型注解推断
    }
  },
  ...
]
```

**所以 docstring 和类型注解不是装饰，是模型能不能用对工具的唯一依据**：

```python
@ai_tools("query_weather")
async def query_weather(city: str, days: int = 1) -> str:
    """查询指定城市未来几天的天气。

    city: 城市名，如 "北京"
    days: 天数，1~7，默认 1
    """
```

## 4. 调用链

```
用户 @机器人 提问
  → ai_chat_main()                       chat.py
      → 组装 messages（system prompt + 历史 + 本轮问题）
      → call_loop(prompt, messages, tools=generate_ai_tools_spec())
           → 调 DeepSeek
           → 模型返回 tool_calls？
                ├─ 是 → 查 command_tools[name]
                │        ├─ 模块被禁用 → 回灌「已被禁用，请勿再调用」
                │        ├─ 函数不存在 → 回灌错误
                │        └─ 执行 → 结果回灌给模型 → 继续循环
                └─ 否 → 返回最终文本
      → 文本 → 回复
```

## 5. 工具函数的约定

| 项 | 要求 |
|---|---|
| 参数 | 必须带类型注解（`str` / `int` / `bool`） |
| 返回 | 字符串（模型能看到的内容） |
| docstring | 说明**用途 + 参数含义**，越具体越好 |
| 副作用 | 可以发消息（用 `push` 或 `context`），但记得告诉模型"已发送" |
| 异常 | 自己捕获并返回错误描述，别让异常冒出去 |

```python
@ai_tools("send_voice")
async def send_voice(text: str) -> str:
    """把文字转成语音发到当前会话。text: 要读的内容"""
    try:
        await tts_send(text)
        return "语音已发送"
    except Exception as e:
        return f"发送失败：{type(e).__name__}"
```

## 6. 权限

工具同样走 RBAC：

```python
@ai_tools("admin_only_tool")
@require_role_async("admin")
async def admin_only_tool(cmd: str) -> str:
    ...
```

非管理员调用会拿到 `No permission`，模型会据此回复用户。

> 注意：工具是**模型**发起的，不是用户直接发起的。
> 模型可能被用户话术诱导去调用高权限工具，所以**高权限操作一定要加 `admin`**。

## 7. 命令 + 工具双注册

同一个函数可以既当命令又当工具：

```python
@ai_tools("get_date")
@command("/time")
@require_role("user")
def show_time() -> str:
    """显示当前时间"""
    return datetime.datetime.now().isoformat()
```

这样用户在群里可以 `/time`，也可以说"现在几点"让模型调。

## 8. 排查

| 现象 | 原因 |
|---|---|
| 模型不调用工具 | docstring 太模糊，或参数说明缺失 |
| 调用报参数错误 | 类型注解缺失/不匹配 |
| 调用了但没反应 | 模块被禁用（`/module list`） |
| 一直不回复 | 工具里抛了未捕获异常，看日志 |

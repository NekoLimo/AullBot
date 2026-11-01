# src/aullbot/chat.py
import json
from pathlib import Path
import datetime
import inspect
from typing import Literal
from openai import OpenAI
from aullbot import settings
from aullbot.tools import generate_ai_tools_spec, ai_tools_map
from aullbot.history_utils import manager
from aullbot.rbac import require_role_async
from aullbot.module_manager import mm

alarm_schedule = {}


# print(ai_tools)

# 全部来自环境变量（.env），见 src/aullbot/settings.py
MAX_TOOL_ITERATIONS: int = settings.MAX_TOOL_ITERATIONS
MODEL: str = settings.MODEL
THINKING_ENABLED: str = settings.THINKING
EFFORT: Literal["low", "high", "max"] = settings.EFFORT  # type: ignore[assignment]


# 客户端在导入期创建：宁可启动多花几秒，也不让用户发第一条消息时
# 卡在 import openai 上（那里的延迟会被误认为机器人挂了）。
client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
print(f"[chat] {settings.describe()}")


def call_ai(
    prompt: dict,
    messages: list[dict],
    model=MODEL,
    tools=None,
    effort: Literal["low", "high", "max"] = EFFORT,
    thinking=THINKING_ENABLED,
):
    if tools is not None:
        response = client.chat.completions.create(
            model=model,
            messages=[prompt] + messages,
            tools=tools,
            reasoning_effort=effort,
            extra_body={"thinking": {"type": thinking}},
            stream=False,
        )
        return response
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[prompt] + messages,
            reasoning_effort=effort,
            extra_body={"thinking": {"type": thinking}},
            stream=False,
        )
        return response


async def call_loop(prompt, messages, tools, callback=None):  # 改为 async
    count = 0
    while True:
        count += 1
        response = call_ai(prompt=prompt, messages=messages, tools=tools)
        assistant_message = response.choices[0].message
        messages.append(assistant_message)

        if not assistant_message.tool_calls:
            msg_result = await callback(text=assistant_message.content)
            print("[AI]", assistant_message.content)
            return (messages, msg_result)

        if assistant_message.content:
            msg_result = await callback(text=assistant_message.content)
            print("[AI]", assistant_message.content)

        if count > MAX_TOOL_ITERATIONS:
            for tc in assistant_message.tool_calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "工具调用次数到达上限",
                    }
                )
                print("[Tools] 工具调用次数达到上限")
            final_response = call_ai(prompt=prompt, messages=messages)
            final_message = final_response.choices[0].message
            messages.append(final_message)
            msg_result = await callback(text=final_message.content)
            print("[AI]", final_message.content)
            return (messages, msg_result)
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name  # type: ignore
            tool_args = json.loads(tool_call.function.arguments)  # type: ignore
            tool_func = ai_tools_map.get(tool_name)
            print(f"[Tool] Calling {tool_name}({tool_args})")
            if not tool_func:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": "unknown tools",
                    }
                )
            elif not mm.is_tool_enabled(tool_name):
                # 工具清单里已过滤，但模型仍可能凭上下文/幻觉发出调用
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"工具 {tool_name} 所属模块已被禁用，请勿再调用",
                    }
                )
            else:
                # 用 inspect 判断异步函数，并用 await 直接调用
                if inspect.iscoroutinefunction(tool_func):
                    try:
                        tool_result = await tool_func(**tool_args)
                    except Exception as e:
                        tool_result = f"工具执行出错: {e}"
                else:
                    try:
                        tool_result = tool_func(**tool_args)
                    except Exception as e:
                        tool_result = f"工具执行出错: {e}"

                tool_result = str(tool_result)
                print(f"[Tool] {tool_name}({tool_args}) -> {tool_result}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )


@require_role_async("user")
async def ai_chat_main(
    chat_id: str | int, chat_type: int, metadata: str | dict, callback=None
) -> str:  # 改为 async
    metadata = str(metadata)
    # 走 load_config：路径由 HistoryManager 决定（不依赖工作目录），
    # 且文件缺失时返回 {}，不会出现 [] .get() 崩溃
    chat_config = manager.load_config(chat_id=chat_id, chat_type=chat_type)
    prompt = chat_config.get("prompt") or []
    if prompt:
        prompt = prompt[0]
    else:
        fallback = manager.read_json(str(Path(__file__).parents[2] / "bot_data" / "system_prompt.json"))
        if not isinstance(fallback, dict) or not fallback.get("content"):
            # 系统提示词缺失/损坏时给一个最小可用的，避免把 [] 塞进 messages
            fallback = {"role": "system", "content": "You are a helpful assistant."}
        prompt = fallback

    if not manager.chat_exists(chat_id, chat_type):
        initial_messages = []
    else:
        initial_messages = manager.read_history(chat_id, chat_type)

    initial_messages.append({"role": "user", "content": metadata})
    history = await call_loop(
        prompt=prompt,
        messages=initial_messages,
        tools=generate_ai_tools_spec(),
        callback=callback,
    )  # await

    manager.save_history(chat_id, chat_type, history[0])

    return history[1]


def set_metadata(
    user_id: str | int | None, name: str | None, content: str, chat_type: str
) -> str:
    if user_id is None:
        user_id = 114514
    user_id = int(user_id)
    now = datetime.datetime.now()
    formatted = f"{now.year}-{now.month}-{now.day} {now.hour:02d}:{now.minute:02d}"
    metadata = {
        "user_id": user_id,
        "user_name": name,
        "current_time": formatted,
        "message_content": content,
        "chat_type": chat_type,
    }
    return str(metadata)

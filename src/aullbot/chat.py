# src/aullbot/chat.py
import os
import json
import datetime
import inspect
from typing import Literal
from openai import OpenAI
from aullbot.tools import generate_ai_tools_spec, ai_tools_map
from aullbot.history_utils import HistoryManager
from aullbot.rbac import require_role_async

ai_tools = generate_ai_tools_spec()

alarm_schedule={}


print(ai_tools)

MAX_TOOL_ITERATIONS: int = 5
MODEL: str = "deepseek-v4-pro"
THINKING_ENABLED: str = "disabled"
EFFORT: Literal["low", "high", "max"] = "high"  # high == low


client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com"
)


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


async def call_loop(
    prompt, messages, tools, callback=None, group_id=None
):  # 改为 async
    count = 0
    while True:
        count += 1
        response = call_ai(prompt=prompt, messages=messages, tools=tools)
        assistant_message = response.choices[0].message
        messages.append(assistant_message)

        if not assistant_message.tool_calls:
            if callback:
                msg_result = await callback(
                    group_id, text=assistant_message.content
                )
                print("[AI]", assistant_message.content)
                return (messages, msg_result)

        if assistant_message.content:
            if callback:
                msg_result = await callback(
                    group_id, text=assistant_message.content
                )
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
            if callback:
                msg_result = await callback(
                    group_id_, text=final_message.content
                )
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


manager = HistoryManager("./bot_data")


@require_role_async("user")
async def ai_chat_main(
    chat_id: str | int,
    chat_type: int,
    metadata: str | dict,
    callback=None,
    group_id=None,
) -> str:  # 改为 async
    metadata = str(metadata)
    chat_route = {0:"group",1:"private"}
    prompt = manager.read_json(f"./bot_data/{chat_route.get(int(chat_type))}/{chat_id}/config.json").get("prompt",[])
    if prompt:
        prompt = prompt[0]
    else:
        prompt = manager.read_json("./bot_data/system_prompt.json")

    if not manager.chat_exists(chat_id, chat_type):
        initial_messages = []
    else:
        initial_messages = manager.read_history(chat_id, chat_type)

    initial_messages.append({"role": "user", "content": metadata})
    history = await call_loop(
        prompt=prompt,
        messages=initial_messages,
        tools=ai_tools,
        callback=callback,
        group_id=group_id,
    )  # await

    manager.save_history(chat_id, chat_type, history[0])

    return history[1]


def set_metadata(user_id: str | int | None, name: str | None, content: str, chat_type:str) -> str:
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
        "chat_type": chat_type
    }
    return str(metadata)

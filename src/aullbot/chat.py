import os
import json
import datetime
import inspect
from typing import Literal
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
from aullbot.private_plugins import generate_ai_tools_spec, ai_tools_map
from aullbot.history_utils import HistoryManager, serialize_messages

ai_tools = generate_ai_tools_spec()

MAX_TOOL_ITERATIONS: int = 5
MODEL: str = "deepseek-v4-pro"
THINKING_ENABLED: str = "disabled"
EFFORT:Literal["low", "high", "max"] = "max" # high == low


client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com"
)


def call_ai(
    prompt: dict,
    messages:list[dict],
    model=MODEL,
    tools=None,
    effort: Literal["low", "high", "max"]=EFFORT,
    thinking=THINKING_ENABLED
):
   if tools is not None:
        response = client.chat.completions.create(
            model=model,
            messages=[prompt] + messages,
            tools=tools,
            reasoning_effort=effort,
            extra_body={"thinking": {"type": thinking}},
            stream=False
        )
        return response
   else:
        response = client.chat.completions.create(
            model=model,
            messages=[prompt] + messages,
            reasoning_effort=effort,
            extra_body={"thinking": {"type": thinking}},
            stream=False
        )
        return response


async def call_loop(prompt, messages, tools):  # 改为 async
    count = 0
    while True:
        count += 1
        response = call_ai(
            prompt=prompt,
            messages=messages, 
            tools=tools
        )
        assistant_message = response.choices[0].message
        messages.append(assistant_message)

        if not assistant_message.tool_calls:
            return messages

        if count >= MAX_TOOL_ITERATIONS:
            for tc in assistant_message.tool_calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "工具调用次数到达上限",
                    }
                )
            final_response = call_ai(
                prompt=prompt,
                messages=messages
            )
            final_message = final_response.choices[0].message
            messages.append(final_message)
            return messages

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
            


manager = HistoryManager("./.history")


async def ai_chat_main(
    chat_id: str | int, chat_type: int, metadata: str | dict
) -> str:  # 改为 async
    metadata = str(metadata)
    prompt = manager.read_json("./.history/system_prompt.json")

    if not manager.chat_exists(chat_id, chat_type):
        initial_messages = []
    else:
        initial_messages = manager.read_history(chat_id, chat_type)

    initial_messages.append({"role": "user", "content": metadata})
    history = await call_loop(
        prompt=prompt, messages=initial_messages, tools=ai_tools
    )  # await

    manager.save_history(chat_id, chat_type, history)
    if isinstance(history, list) and history:
        if isinstance(history[0], (dict, ChatCompletionMessage)):
            history = serialize_messages(history)

    for msg in reversed(history):
        if msg.get("role") == "assistant":
            return msg.get("content") or ""
    return ""


def set_metadata(user_id: str | int | None, name: str | None, content: str) -> str:
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
    }
    return str(metadata)


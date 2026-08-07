# scr/aullbot/tools/tts.py
import os
import requests
from .. import context
from aullbot.command_registry import ai_tools
import random

def Todo(*args): 
    """占位符"""
    return "todo bro😭"

BASIC_URL = "http://127.0.0.1:2030"
VOICE = "qingya"

async def send_message(file):
    bot = context.get_bot()
    chat_type = context.get_chat_type()
    chat_id = context.get_chat_id()
    if chat_type == 0:  # group
        await bot.api.qq.send_group_record(group_id=chat_id, file=file)
        print("group:", file)
    elif chat_type == 1:  # private
        await bot.api.qq.send_private_record(user_id=chat_id, file=file)
        print("private:", file)

@ai_tools("send_voice")
async def send_voice(text: str) -> str:
    """发送语音消息"""
    API = f"{BASIC_URL}/api/tts?text={text}&speed=10&voice={VOICE}"
    
    file_name = f"tts{random.randint(0,114514)}.wav"
    response = requests.get(API, stream=True)
    with open(os.path.join(context.get_cache_path(), file_name), "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:  # 过滤掉 keep-alive 的空块
                f.write(chunk)
    
    await send_message(file=os.path.join(context.get_cache_path(), file_name))
    return "succeeded"
# scr/aullbot/main.py
# Author: Limo
# ========== 导入模块 ===========
import time
print("------------- 导入已开始 -------------")
start = time.perf_counter()
from ncatbot.app import BotClient
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import *                 # type: ignore
from pathlib import Path
import asyncio
import shlex
import json
import datetime

from aullbot import context
from aullbot import IO_json
from aullbot import llm

end = time.perf_counter()
print(f"------------- 导入耗时：{end - start:.4f} 秒 -------------")

# ========== 初始化 ============

BASE_DIR = Path(__file__).parent.parent.parent  # 项目根目录
CACHE_DIR = BASE_DIR / ".cache"
HISTORY_DIR = BASE_DIR / ".history"

CACHE_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)
bot = BotClient()

IO_json.set_json_path(str(HISTORY_DIR))
GROUP_LIST_FILE = HISTORY_DIR / "group_list.json"
group_list = IO_json.read_json(str(GROUP_LIST_FILE))


# ========== 注册命令 ===========

"""###### 已转移 ######"""

def Todo(*args):
    """占位符"""
    return "Todo bro😭" 

def ai_chat(user_input, chat_id):
    history = IO_json.read_history(chat_id)
    history.append(llm.result("user",user_input))
    # print(history)
    response = llm.dialogue(history)
    message_obj = response.choices[0].message
    message_dict = {
        'role': message_obj.role,
        'content': message_obj.content,
    }
    history.append(message_dict)
    #IO_json.scroll_window(250, history)
    IO_json.write_json(chat_id, history)
    return message_dict["content"]

# ========= 注册命令路由 ==========

"""###### 已转移 ######"""
from aullbot.private_plugins import command_route

# ========== 解析命令 ===========

async def find_command(command, chat_id, information, chat_type=0):
    context.set_context(bot, chat_type, chat_id, cache_path=str(CACHE_DIR))
    try:
        command_tokens = shlex.split(command)
        command_shell = command_tokens[0]
    except:
        # 异常处理,call AIChat
        now = datetime.datetime.now()
        formatted = f"{now.year}-{now.month}-{now.day} {now.hour:02d}:{now.minute:02d}"
        data = {
            'user_id': int(information[0]),
            'user_name': information[1],
            'current_time': formatted,
            'message_content': command
        }
        content = json.dumps(data, ensure_ascii=False)
        print(content)
        ret = ai_chat(content, chat_id)
        print(ret)
        return ret

    if command_shell in command_route:
        print(command_tokens[1:])
        func = command_route[command_shell]
        # 判断函数是否为协程函数，是则 await
        if asyncio.iscoroutinefunction(func):
            ret = await func(command_tokens[1:])
            if ret:
                return ret
            return None
        else:
            ret = func(command_tokens[1:])
            if ret:
                return ret
            return None
    else:
        # 未知命令（调用 AI 聊天）
        now = datetime.datetime.now()
        formatted = f"{now.year}-{now.month}-{now.day} {now.hour:02d}:{now.minute:02d}"
        data = {
            'user_id': int(information[0]),
            'user_name': information[1],
            'current_time': formatted,
            'message_content': command
        }
        content = json.dumps(data, ensure_ascii=False)
        print(content)
        ret = ai_chat(content, chat_id)
        print(ret)
        return ret

# ========== 程序入口 ===========
"""群聊"""
@registrar.qq.on_group_message(priority=100)
async def is_group_me(event: GroupMessageEvent):

    if event.group_id in group_list:
        pass
    else:
        if IO_json.is_group_exists(event.group_id):
            pass
        else:
            IO_json.add_group_list(event.group_id)
            group_list.append(event.group_id)
            
    qq_number = event.sender.user_id
    nickname = event.sender.card or event.sender.nickname
    self_id = event.self_id
    segments = event.message

    # 将每个消息段转为字符串
    parts = []
    for seg in segments:
        if isinstance(seg, At):
            parts.append(f"@{seg.user_id}")
        elif isinstance(seg, PlainText):
            parts.append(seg.text)
        else:
            pass
    
    print(parts)
    # 去除开头或末尾的 @机器人
    if parts and parts[0] == f"@{self_id}":
        parts.pop(0)                     # 移除开头的 @机器人
    if parts and parts[-1] == " ":
        if len(parts) >= 2 and parts and parts[-2] == f"@{self_id}":
            parts.pop(-1)
    if parts and parts[-1] == f"@{self_id}":
        parts.pop(-1)                    # 移除末尾的 @机器人
    
    print(parts)
    
    msg_text = "".join(parts)              # 纯文本，保留空格
    print(msg_text)
    if any(isinstance(seg, At) and str(seg.user_id) == str(self_id) for seg in event.message):
        text_to_send = await find_command(command=msg_text.strip(), chat_id=event.group_id, information=[qq_number,nickname], chat_type=0)
        if text_to_send:
            print("\n"+text_to_send)
            await bot.api.qq.post_group_msg(group_id=event.group_id, text=text_to_send)
            # await event.reply(text=text_to_send, at_sender=False)

"""私聊"""
@registrar.on_private_message(priority=100)
async def is_private_me(event: PrivateMessageEvent):

    if event.user_id in group_list:
        pass
    else:
        if IO_json.is_group_exists(event.user_id):
            pass
        else:
            IO_json.add_group_list(event.user_id)
            group_list.append(event.user_id)
            
    qq_number = event.sender.user_id
    nickname = event.sender.nickname
    self_id = event.self_id
    segments = event.message

    # 将每个消息段转为字符串
    parts = []
    for seg in segments:
        if isinstance(seg, PlainText):
            parts.append(seg.text)
        else:
            pass
    
    print(parts)
    
    msg_text = "".join(parts)              # 纯文本，保留空格
    print(msg_text)
    
    text_to_send = await find_command(command=msg_text.strip(), chat_id=event.user_id, information=[qq_number,nickname], chat_type=1)
    if text_to_send:
        print("\n"+text_to_send)
        await event.reply(text=text_to_send, at_sender=False)

# =========== 调用 ============

if __name__ == "__main__":
    bot.run()
    

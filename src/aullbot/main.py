# scr/aullbot/main.py
# Author: Limo
# ========== 导入模块 ===========
import time

print("------------- 导入已开始 -------------")
start = time.perf_counter()
from ncatbot.app import BotClient
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import *  # type: ignore
from pathlib import Path
import shlex
import inspect

from aullbot.private_plugins import command_route
from aullbot.chat import ai_chat_main, set_metadata
from aullbot import context
from aullbot.history_utils import HistoryManager

end = time.perf_counter()
print(f"------------- 导入耗时：{end - start:.4f} 秒 -------------")

# ========== 初始化 ============

TYPE_GRUOP = 0
TYPE_PRTVATE = 1

BASE_DIR: Path = Path(__file__).parent.parent.parent  # 项目根目录
CACHE_DIR: Path = BASE_DIR / ".cache"
HISTORY_DIR: Path = BASE_DIR / ".history"
GROUP_HISTOYR: Path = HISTORY_DIR / "group"
PRIVATE_HISTORY = HISTORY_DIR / "private"

CACHE_DIR.mkdir(exist_ok=True)
GROUP_HISTOYR.mkdir(exist_ok=True)
PRIVATE_HISTORY.mkdir(exist_ok=True)

history_mgr = HistoryManager(str(HISTORY_DIR))
GROUP_LIST_FILE: Path = HISTORY_DIR / "group_list.json"
group_list = history_mgr.read_json(str(GROUP_LIST_FILE))

bot = BotClient()

# ========== 注册命令 ===========
"""###### 已转移 #####"""
# ========= 注册命令路由 ==========
"""###### 已转移 ######"""
# ========== 解析命令 ===========
COMMAND_NOT_FOUND = -255


async def find_command(command):
    try:
        tokens = shlex.split(command)
        command_name = tokens[0]
        command_args = tokens[1:]
        if command_name in command_route:
            # command_args = " ".join(command_args).strip()
            func = command_route[command_name]
            if inspect.iscoroutinefunction(func):
                sig = inspect.signature(func)
                len_params = len(sig.parameters)
                if len_params == 1:
                    command_args = " ".join(command_args).strip()
                    ret = await func(command_args)
                    return ret if ret else None
                ret = await func(*command_args[:len_params])
                if ret:
                    return ret
                return None
            else:
                sig = inspect.signature(func)
                len_params = len(sig.parameters)
                if len_params == 1:
                    command_args = " ".join(command_args).strip()
                    ret = func(command_args)
                    return ret if ret else None
                ret = func(*command_args[:len_params])
                if ret:
                    return ret
                return None
        else:
            return COMMAND_NOT_FOUND
    except TypeError as e:
        return f"参数错误: {str(e)}"
    except:
        return COMMAND_NOT_FOUND


# ========== 程序入口 ===========
"""群聊"""

group_sender_massage_id = [0, 0, 0]
@registrar.qq.on_group_message(priority=100)
async def is_group_me(event: GroupMessageEvent):
    context.set_context(bot, TYPE_GRUOP, event.group_id, cache_path=str(CACHE_DIR))

    if history_mgr.chat_exists(event.group_id, TYPE_GRUOP):
        pass
    else:
        history_mgr.add_chat_list(event.group_id, TYPE_GRUOP)
        group_list.append(event.group_id)

    # 获取用户的信息
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

    print(f"[System] 原始消息:{parts}")
    # 去除开头或末尾的 @机器人
    if parts and parts[0] == f"@{self_id}":
        parts.pop(0)  # 移除开头的 @机器人
    if parts and parts[-1] == " ":
        if len(parts) >= 2 and parts and parts[-2] == f"@{self_id}":
            parts.pop(-1)
    if parts and parts[-1] == f"@{self_id}":
        parts.pop(-1)  # 移除末尾的 @机器人

    print(f"[System] 处理:{parts}")

    msg_text = "".join(parts)  # 纯文本，保留空格
    msg_text = msg_text.strip()
    print(msg_text)
    if msg_text == "撤回":
        await bot.api.qq.messaging.delete_msg(group_sender_massage_id[-1])
        return
    text_to_send = await find_command(command=msg_text)
    if isinstance(text_to_send, str) and text_to_send:
        print(f"{text_to_send}")
        msg_result = await bot.api.qq.post_group_msg(group_id=event.group_id, text=text_to_send)
        # await event.reply(text=text_to_send, at_sender=False)
        group_sender_massage_id.append(msg_result["message_id"])
        group_sender_massage_id.pop(0)
        return
    if any(
        isinstance(seg, At) and str(seg.user_id) == str(self_id)
        for seg in event.message
    ):
        print("call ai")
        result = await ai_chat_main(
            chat_id=event.group_id,
            chat_type=0,
            metadata=set_metadata(qq_number, nickname, msg_text),
        )
        print("[AI]", result)
        msg_result = await bot.api.qq.post_group_msg(group_id=event.group_id, text=result)
        group_sender_massage_id.append(msg_result["message_id"])
        group_sender_massage_id.pop(0)
            


"""私聊"""

@registrar.on_private_message(priority=100)
async def is_private_me(event: PrivateMessageEvent):
    context.set_context(bot, TYPE_PRTVATE, event.user_id, cache_path=str(CACHE_DIR))

    if history_mgr.chat_exists(event.user_id, TYPE_PRTVATE):
        pass
    else:
        history_mgr.add_chat_list(event.user_id, TYPE_PRTVATE)
        group_list.append(event.user_id)

    qq_number = event.sender.user_id
    nickname = event.sender.nickname
    segments = event.message

    # 将每个消息段转为字符串
    parts = []
    for seg in segments:
        if isinstance(seg, PlainText):
            parts.append(seg.text)
        else:
            pass

    print(parts)

    msg_text = "".join(parts)  # 纯文本，保留空格
    msg_text = msg_text.strip()
    print(msg_text)

    text_to_send = await find_command(command=msg_text)
    if text_to_send and type(text_to_send) == str:
        print(f"\n{text_to_send}")
        await event.reply(text=text_to_send, at_sender=False)
    elif text_to_send == COMMAND_NOT_FOUND:
        print("[System] Calling ai")
        result = await ai_chat_main(
            chat_id=event.user_id,
            chat_type=0,
            metadata=set_metadata(qq_number, nickname, msg_text),
        )
        print("[AI]", result)
        await bot.api.qq.post_private_msg(user_id=event.user_id, text=result)


# =========== 调用 ============

if __name__ == "__main__":
    bot.run()

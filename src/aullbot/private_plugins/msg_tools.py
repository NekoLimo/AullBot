# src/aullbot/private_plugins/msg_tools.py
from pathlib import Path
from .. import context
from .command_registry import ai_tools
from os.path import join

def Todo(*args):
    """占位符"""
    return "Todo bro😭"


@ai_tools("send_message")
async def send_text(text: str) -> str:
    '''发送消息到群组或私聊'''
    BOT = context.get_bot()
    CHAT_TYPE = context.get_chat_type()
    CHAT_ID = context.get_chat_id()
    try:
        if CHAT_TYPE == 0:  # group
            await BOT.api.qq.post_group_msg(group_id=CHAT_ID, text=text, )
            print("group:", text)
            return "succeeded"
        elif CHAT_TYPE == 1:  # private
            await BOT.api.qq.post_private_msg(user_id=CHAT_ID, text=text)
            print("private:", text)
            return "succeeded"
    except Exception as e:
        print(f"Error sending message: {e}")
        return f"Error sending message: {e}"

@ai_tools("get_stickers_list")
def get_stickers_list() -> str:
    '''获取表情包列表'''
    return '\n'.join([f.name for f in Path('./meme').iterdir() if f.is_file()])

@ai_tools("send_sticker")
async def send_sticker(sticker_name: str):
    '''发送消息到群组或私聊(需要后缀名)'''
    BOT = context.get_bot()
    CHAT_TYPE = context.get_chat_type()
    CHAT_ID = context.get_chat_id()
    try:
        if CHAT_TYPE == 0:  # group
            if sticker_name:
                await BOT.api.qq.send_group_sticker(CHAT_ID, image=join("./meme", sticker_name))
                print("group:", sticker_name)
                return "succeeded"
        elif CHAT_TYPE == 1:  # private
            if sticker_name:
                await BOT.api.qq.send_private_sticker(CHAT_ID, image=join("./meme", sticker_name))
                print("private:", sticker_name)
                return "succeeded"
    except Exception as e:
        print(f"Error sending message: {e}")
        return f"Error sending message: {e}"

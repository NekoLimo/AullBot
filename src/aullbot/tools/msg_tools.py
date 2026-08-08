# src/aullbot/tools/msg_tools.py
from pathlib import Path
from .. import context
from aullbot.command_registry import ai_tools
from os.path import join
from ncatbot.types import MessageArray
from ncatbot.types.qq import parse_cq_code_to_onebot11

def Todo(*args):
    """占位符"""
    return "Todo bro😭"


stickers_path = Path(__file__).parent.parent.parent.parent / "meme"

@ai_tools("send_message")
async def send_text(text: str) -> str:
    '''发送消息到群组或私聊'''
    BOT = context.get_bot()
    CHAT_TYPE = context.get_chat_type()
    CHAT_ID = context.get_chat_id()
    try:
        if CHAT_TYPE == 0:  # group
            await BOT.api.qq.send_group_text(group_id=CHAT_ID, text=text)
            print("group:", text)
            return "succeeded"
        elif CHAT_TYPE == 1:  # private
            await BOT.api.qq.send_private_text(user_id=CHAT_ID, text=text)
            print("private:", text)
            return "succeeded"
    except Exception as e:
        print(f"Error sending message: {e}")
        return f"Error sending message: {e}"

@ai_tools("get_stickers_list")
def get_stickers_list() -> str:
    '''获取表情包列表'''
    return '\n'.join([f.name for f in stickers_path.iterdir() if f.is_file()])

@ai_tools("send_sticker")
async def send_sticker(sticker_name: str):
    '''
    发送消息到群组或私聊(需要后缀名)
    执行本工具前，必须先调用 get_stickers_list 获取真实存在的文件名。
    如果传入不存在的文件名，发送将永久失败。
    '''
    BOT = context.get_bot()
    CHAT_TYPE = context.get_chat_type()
    CHAT_ID = context.get_chat_id()
    try:
        if CHAT_TYPE == 0:  # group
            if sticker_name:
                await BOT.api.qq.send_group_sticker(CHAT_ID, image=str(stickers_path / sticker_name))
                print("group:", sticker_name)
                return "succeeded"
        elif CHAT_TYPE == 1:  # private
            if sticker_name:
                await BOT.api.qq.send_private_sticker(CHAT_ID, image=join(stickers_path / sticker_name))
                print("private:", sticker_name)
                return "succeeded"
    except Exception as e:
        print(f"Error sending message: {e}")
        return f"Error sending message: {e}"

@ai_tools("send_qc")
async def send_qc(text: str) -> str:
    """
    接受标准CQ码，例如：
    [CQ:at,qq=3944649615] 这是一条AT消息
    当需要使用CQ码，时请调用此工具
    """
    BOT = context.get_bot()
    CHAT_TYPE = context.get_chat_type()
    CHAT_ID = context.get_chat_id()
    response = MessageArray.from_list(parse_cq_code_to_onebot11(text))
    try:
        if CHAT_TYPE == 0:  # group
            await BOT.api.qq.post_group_array_msg(group_id=CHAT_ID, msg=response)
            print("group:", text)
            return "succeeded"
        elif CHAT_TYPE == 1:  # private
            await BOT.api.qq.post_private_array_msg(user_id=CHAT_ID, msg=response)
            print("private:", text)
            return "succeeded"
    except Exception as e:
        print(f"Error sending message: {e}")
        return f"Error sending message: {e}"

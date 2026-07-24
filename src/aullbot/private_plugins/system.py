# src/aullbot/private_plugins/system.py
from .command_registry import command, command_registry, command_tools, ai_tools
import base64
import subprocess as sbs
import os
import datetime
import base64
import shlex


def Todo(*args):
    """占位符"""
    return "Todo bro😭"

def help_command(cmd: str = None) -> str: # type: ignore
    """
    help [命令名]
    无参数：列出所有可用命令名称。
    有参数：显示该命令的详细文档。
    """
    if cmd is None or cmd == "":
        cmds = [name for name in command_registry.keys() if name != "help"]
        return "可用命令：\n" + "\n".join(cmds)
    else:
        func = command_registry.get(cmd)
        if func is None:
            return f"未知命令：{cmd}"
        return func.__doc__.strip() if func.__doc__ else "该命令无帮助文档"
    
def help_ai_tools(tool: str = None) -> str: # type: ignore
    """
    help_ai_tools [工具名]
    无参数：列出所有可用 AI 工具名称。
    有参数：显示该工具的详细文档。
    """
    if tool is None or tool == "":
        tools = list(command_tools.keys())
        return "可用 AI 工具：\n" + "\n".join(tools)
    else:
        func = command_tools.get(tool)
        if func is None:
            return f"未知 AI 工具：{tool}"
        return func.__doc__.strip() if func.__doc__ else "该工具无帮助文档"

@command("/say")
def say(text: str) -> str:
    """复读机"""
    return text

@command("/vme50")
def crazy_thursday_check():
    """
    疯狂疯狂星期四,9块9块9块9
    """
    # 获取当前日期时间
    now = datetime.datetime.now()
    # weekday(): 周一为0，周二为1，...，周日为6，所以周四为3
    if now.weekday() == 3:
        return "明天再来要一遍就给你"
    else:
        return "今天不是疯狂星期四凭什么来要"

@ai_tools("get_date")
@command("/time")     
def show_time() -> str:
    """显示时间"""
    now = datetime.datetime.now()
    return f"{now}"

@ai_tools("base64_decode")
@command("/b64de")  
def base64_decode(text: str) -> str:
    """
    将 Base64 字符串解码为 UTF-8 文本。
    参数： Base64 文本，多参数丢弃
    返回解码后的文本，失败时返回错误信息。
    """
    if not text:
        return '解码失败: text为空'
    try:
        decoded_bytes = base64.b64decode(text)
        return decoded_bytes.decode('utf-8')
    except Exception as e:
        return f'解码失败: {e}'

@ai_tools("base64_encode")
@command("/b64en")
def base64_encode(text: str) -> str:
    """Base64 编码：将文本转换为 base64 字符串"""
    if not text:
        return '编码失败: text为空'
    try:
        encoded_bytes = base64.b64encode(text.encode('utf-8'))
        return encoded_bytes.decode('utf-8')
    except Exception as e:
        return f'编码失败: {e}'

@ai_tools("ascii_decode")
@command("/ascii_de")
def ascii_decode(text: str) -> str:
    chars = []
    for item in text.split():
        try:
            chars.append(chr(int(item)))
        except Exception as e:
            return f'解码失败: 无效的ASCII码 {item} - {e}'
    return ''.join(chars)

@ai_tools("ascii_encode")
@command("/ascii_en")
def ascii_encode(text: str) -> str:
    """文本转 ASCII 码列表：将文本转换为十进制 ASCII 码，空格分隔"""
    if not text:
        return '编码失败: text为空'
    try:
        ascii_codes = []
        for ch in text:
            code = ord(ch)
            ascii_codes.append(str(code))
        return ' '.join(ascii_codes)
    except Exception as e:
        return f'编码失败: {e}'

@ai_tools("text_to_bin")
@command("/txt2bin")
def text_to_bin(text: str) -> str:
    """文本转二进制：UTF-8 编码，每个字节 8 位，空格分隔"""
    if not text:
        return '编码失败: 没有输入'
    try:
        utf8_bytes = text.encode('utf-8')
        return ' '.join(f'{byte:08b}' for byte in utf8_bytes)
    except Exception as e:
        return f'编码失败: {e}'

@ai_tools("bin_to_text")
@command("/bin2txt")
def bin_to_text(text: str) -> str:
    """二进制转文本：
    1. 若 args 长度 > 1，则每个元素是一个 8 位二进制串，合并后 UTF-8 解码。
    2. 若 args 长度为 1，则视作连续二进制串：
       - 先尝试 8 位一组 UTF-8 解码；
       - 失败则尝试 4 位一组转十进制（空格分隔）；
       - 长度不合法返回 '无效的二进制'。
    """
    if not text:
        return '解码失败: 没有输入'

    # 情况1：多个独立二进制片段（即用户以空格分隔的输入）
    if len(text.split()) > 1:
        try:
            byte_data = bytes(int(part, 2) for part in text.split())
            return byte_data.decode('utf-8')
        except Exception as e:
            return f'解码失败: {e}'

    # 情况2：单个连续的二进制串
    raw = text.split()[0].strip()
    if not raw:
        return '解码失败: 空字符串'

    length = len(raw)
    # 先尝试 8 位一组（UTF-8 解码）
    if length % 8 == 0:
        groups = [raw[i:i+8] for i in range(0, length, 8)]
        try:
            byte_data = bytes(int(g, 2) for g in groups)
            return byte_data.decode('utf-8')
        except (ValueError, UnicodeDecodeError):
            # 若 8 位分组不能正确解码为 UTF-8，继续尝试 4 位分组
            pass

    # 回退：4 位一组转十进制数字（空格分隔）
    if length % 4 != 0:
        return '无效的二进制'

    groups = [raw[i:i+4] for i in range(0, length, 4)]
    decimals = []
    for g in groups:
        try:
            decimals.append(str(int(g, 2)))
        except ValueError:
            return f'无效的二进制: {g}'
    return ' '.join(decimals)
    
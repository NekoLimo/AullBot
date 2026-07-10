# scr/private_plugins/system.py
from .command_registry import command, command_registry
import base64
import subprocess as sbs
import os
import datetime
import base64


def Todo(*args):
    """占位符"""
    return "Todo bro😭"
   
def help_command(args):
    """
    help [命令名]
    无参数：列出所有可用命令名称。
    有参数：显示该命令的详细文档。
    """
    if not args:
        # 收集所有命令名称（排除 help 自身）
        cmds = [cmd for cmd in command_registry.keys() if cmd != "help"]
        # 返回换行分隔的命令列表
        return "可用命令：\n" + "\n".join(cmds)
    else:
        cmd = args[0]
        func = command_registry.get(cmd)
        if func is None:
            return f"未知命令：{cmd}"
        return func.__doc__.strip() if func.__doc__ else "该命令无帮助文档"

@command("say")
def say(args):
    """复读机"""
    res = ""
    for i in args:
        res = res + i + " "
    return res

# @command("sh")
def run_shell_command(args):
    """运行一条Linux命令"""
    if not args:
        return """运行一条Linux命令,不支持shell语法"""
    forbidden_command = [
        "rm", "dd", "mkfs", "fdisk", "parted", "chomd", "chown", "kill", "ssh", "reboot", "init", "telinit", ":(){", ".(){", "su", "sudo", "python3","python","wget","curl","alias","bash","sh","zsh","gcc","g++","pip","ping","sleep"
    ]
    print(args[0])
    if args[0] in forbidden_command:
        return "这个不可以喵！\n err:您运行的命令在黑名单中"
    for i in forbidden_command:
        if i in args[0]:
            return "这个不可以喵\n err:您运行的命令在黑名单中"
    try:
        r = sbs.check_output(args,text=True,timeout=5,encoding="utf-8")
        return r.strip()
    except Exception as e:
        return f'运行失败了喵（哭）\n err:{e}'

@command("flag")
def return_flag(args):
    """none"""
    if os.environ.get('FLAG') == args[0]:
        return f"{os.environ.get('FLAG')} is TRUE"
   
@command("时间")     
def show_time(*args):
    """显示时间"""
    now = datetime.datetime.now()
    return f"现在是\n{now}喵！"
  
@command("b64de")  
def base64_decode(args):
    """
    将 Base64 字符串解码为 UTF-8 文本。
    参数： Base64 文本，多参数丢弃
    返回解码后的文本，失败时返回错误信息。
    """
    if not args:
        return '解码失败: args为空'
    try:
        decoded_bytes = base64.b64decode(args[0])
        return decoded_bytes.decode('utf-8')
    except Exception as e:
        return f'解码失败: {e}'

@command("b64en")
def base64_encode(args):
    """Base64 编码：将文本转换为 base64 字符串"""
    if not args:
        return '编码失败: args为空'
    res = ""
    for i in args:
        res = res + i + " "
    try:
        encoded_bytes = base64.b64encode(res.encode('utf-8'))
        return encoded_bytes.decode('utf-8')
    except Exception as e:
        return f'编码失败: {e}'

@command("ascii_de")
def ascii_decode(args):
    chars = []
    for item in args:
        try:
            chars.append(chr(int(item)))
        except Exception as e:
            return f'解码失败: 无效的ASCII码 {item} - {e}'
    return ''.join(chars)

@command("ascii_en")
def ascii_encode(args):
    """文本转 ASCII 码列表：将文本转换为十进制 ASCII 码，空格分隔"""
    if not args:
        return '编码失败: args为空'
    res = ""
    for i in args:
        res = res + i + " "
    try:
        ascii_codes = []
        for ch in res:
            code = ord(ch)
            ascii_codes.append(str(code))
        return ' '.join(ascii_codes)
    except Exception as e:
        return f'编码失败: {e}'

@command("txt2bin")
def text_to_bin(args):
    """文本转二进制：UTF-8 编码，每个字节 8 位，空格分隔"""
    if not args:
        return '编码失败: 没有输入'
    res = ""
    for i in args:
        res = res + i + " "
    try:
        utf8_bytes = res.encode('utf-8')
        return ' '.join(f'{byte:08b}' for byte in utf8_bytes)
    except Exception as e:
        return f'编码失败: {e}'

@command("bin2txt")
def bin_to_text(args):
    """二进制转文本：
    1. 若 args 长度 > 1，则每个元素是一个 8 位二进制串，合并后 UTF-8 解码。
    2. 若 args 长度为 1，则视作连续二进制串：
       - 先尝试 8 位一组 UTF-8 解码；
       - 失败则尝试 4 位一组转十进制（空格分隔）；
       - 长度不合法返回 '无效的二进制'。
    """
    if not args:
        return '解码失败: 没有输入'

    # 情况1：多个独立二进制片段（即用户以空格分隔的输入）
    if len(args) > 1:
        try:
            byte_data = bytes(int(part, 2) for part in args)
            return byte_data.decode('utf-8')
        except Exception as e:
            return f'解码失败: {e}'

    # 情况2：单个连续的二进制串
    raw = args[0].strip()
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
    
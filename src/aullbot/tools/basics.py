# src/aullbot/tools/Basics.py
from aullbot.command_registry import command, ai_tools
from aullbot.rbac import require_role, require_role_async
from aullbot.module_meta import ModuleMeta
import asyncio
import base64
import datetime

from aullbot import context, push

MODULE = ModuleMeta(
    name="basics",
    author="Limo",
    description="基础命令：时间、Base64/ASCII/二进制编解码",
    version="0.2.5",
    default_enabled=True,   # 核心模块，别关
    tags=("core",),
    readme="提供基础命令。",
)


def Todo(*args):
    """占位符"""
    return "Todo bro😭"

SAY_MAX_DELAY = 86400  # 最长延迟 1 天
_say_tasks: set[asyncio.Task] = set()


async def _delayed_say(delay: float, chat_type: int, chat_id, body: str) -> None:
    try:
        await asyncio.sleep(delay)
        if not await push.send(chat_type, chat_id, body):
            print(f"[say] 定时发送失败 chat={chat_type}/{chat_id}")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[say] 定时发送异常: {type(e).__name__}: {e}")


@command("/say")
@require_role_async("user")
async def say(text: str = "", delay=0) -> str:
    """复读机：/say 内容 [延迟秒数]（延迟默认 0）

    参数按 shell 规则切分，内容含空格时请用引号：
        /say 你好
        /say "a b c" 30      # 30 秒后发送 "a b c"
        /say "今天 天气 不错"
    """
    body = (text or "").strip()

    # 框架按空格切参数，delay 拿到的是字符串；
    # 不是数字说明用户只是想发一句带空格的话，把它拼回正文
    secs = 0.0
    if delay not in (0, None) and str(delay).strip():
        raw_delay = str(delay).strip()
        try:
            secs = float(raw_delay)
        except ValueError:
            body = f"{body} {raw_delay}".strip()

    if not body:
        return '用法：/say 内容 [延迟秒数]（延迟默认 0）\n内容含空格请加引号，如 /say "a b c" 30'
    if secs < 0:
        return "延迟不能是负数"
    if secs > SAY_MAX_DELAY:
        return f"延迟不能超过 {SAY_MAX_DELAY} 秒（1 天）"
    if secs <= 0:
        return body

    task = asyncio.create_task(
        _delayed_say(secs, context.get_chat_type(), context.get_chat_id(), body)
    )
    _say_tasks.add(task)
    task.add_done_callback(_say_tasks.discard)
    return f"已排队：{int(secs)} 秒后发送（共 {len(body)} 字）"


@ai_tools("get_date")
@command("/time")
@require_role("user")
def show_time() -> str:
    """显示时间"""
    now = datetime.datetime.now()
    return f"{now}"


@ai_tools("base64_decode")
@command("/b64de")
@require_role("user")
def base64_decode(text: str) -> str:
    """
    将 Base64 字符串解码为 UTF-8 文本。
    参数： Base64 文本，多参数丢弃
    返回解码后的文本，失败时返回错误信息。
    """
    if not text:
        return "解码失败: text为空"
    try:
        decoded_bytes = base64.b64decode(text)
        return decoded_bytes.decode("utf-8")
    except Exception as e:
        return f"解码失败: {e}"


@ai_tools("base64_encode")
@command("/b64en")
@require_role("user")
def base64_encode(text: str) -> str:
    """Base64 编码：将文本转换为 base64 字符串"""
    if not text:
        return "编码失败: text为空"
    try:
        encoded_bytes = base64.b64encode(text.encode("utf-8"))
        return encoded_bytes.decode("utf-8")
    except Exception as e:
        return f"编码失败: {e}"


@ai_tools("ascii_decode")
@command("/ascii_de")
@require_role("user")
def ascii_decode(text: str) -> str:
    chars = []
    for item in text.split():
        try:
            chars.append(chr(int(item)))
        except Exception as e:
            return f"解码失败: 无效的ASCII码 {item} - {e}"
    return "".join(chars)


@ai_tools("ascii_encode")
@command("/ascii_en")
@require_role("user")
def ascii_encode(text: str) -> str:
    """文本转 ASCII 码列表：将文本转换为十进制 ASCII 码，空格分隔"""
    if not text:
        return "编码失败: text为空"
    try:
        ascii_codes = []
        for ch in text:
            code = ord(ch)
            ascii_codes.append(str(code))
        return " ".join(ascii_codes)
    except Exception as e:
        return f"编码失败: {e}"


@ai_tools("text_to_bin")
@command("/txt2bin")
@require_role("user")
def text_to_bin(text: str) -> str:
    """文本转二进制：UTF-8 编码，每个字节 8 位，空格分隔"""
    if not text:
        return "编码失败: 没有输入"
    try:
        utf8_bytes = text.encode("utf-8")
        return " ".join(f"{byte:08b}" for byte in utf8_bytes)
    except Exception as e:
        return f"编码失败: {e}"


@ai_tools("bin_to_text")
@command("/bin2txt")
@require_role("user")
def bin_to_text(text: str) -> str:
    """二进制转文本：
    1. 若 args 长度 > 1，则每个元素是一个 8 位二进制串，合并后 UTF-8 解码。
    2. 若 args 长度为 1，则视作连续二进制串：
       - 先尝试 8 位一组 UTF-8 解码；
       - 失败则尝试 4 位一组转十进制（空格分隔）；
       - 长度不合法返回 '无效的二进制'。
    """
    if not text:
        return "解码失败: 没有输入"

    # 情况1：多个独立二进制片段（即用户以空格分隔的输入）
    if len(text.split()) > 1:
        try:
            byte_data = bytes(int(part, 2) for part in text.split())
            return byte_data.decode("utf-8")
        except Exception as e:
            return f"解码失败: {e}"

    # 情况2：单个连续的二进制串
    raw = text.split()[0].strip()
    if not raw:
        return "解码失败: 空字符串"

    length = len(raw)
    # 先尝试 8 位一组（UTF-8 解码）
    if length % 8 == 0:
        groups = [raw[i : i + 8] for i in range(0, length, 8)]
        try:
            byte_data = bytes(int(g, 2) for g in groups)
            return byte_data.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            # 若 8 位分组不能正确解码为 UTF-8，继续尝试 4 位分组
            pass

    # 回退：4 位一组转十进制数字（空格分隔）
    if length % 4 != 0:
        return "无效的二进制"

    groups = [raw[i : i + 4] for i in range(0, length, 4)]
    decimals = []
    for g in groups:
        try:
            decimals.append(str(int(g, 2)))
        except ValueError:
            return f"无效的二进制: {g}"
    return " ".join(decimals)


@command("/v50")
@command("/vivo50")
@command("/vme50")
@require_role("user")
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

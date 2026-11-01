# scr/aullbot/main.py
# Author: Limo
# ========== 导入模块 ===========
import time

print("------------- 导入已开始 -------------")
start = time.perf_counter()
from ncatbot.app import BotClient
from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.types import MessageArray
from ncatbot.types.qq import parse_cq_code_to_onebot11
from ncatbot.types import *  # type: ignore
from pathlib import Path
import shlex
import inspect

from aullbot.tools import command_route
from aullbot.user_utils import command_manager_map
from aullbot.chat import ai_chat_main, set_metadata
from aullbot import context
from aullbot import push
from aullbot.history_utils import manager as history_mgr
from aullbot.module_manager import mm

end = time.perf_counter()
print(f"------------- 导入耗时：{end - start:.4f} 秒 -------------")

# ========== 初始化 ============

TYPE_GROUP = 0
TYPE_PRTVATE = 1

BASE_DIR: Path = Path(__file__).parent.parent.parent  # 项目根目录
CACHE_DIR: Path = BASE_DIR / ".cache"
HISTORY_DIR: Path = BASE_DIR / "bot_data"
GROUP_HISTOYR: Path = HISTORY_DIR / "group"
PRIVATE_HISTORY = HISTORY_DIR / "private"

CACHE_DIR.mkdir(exist_ok=True)
GROUP_HISTOYR.mkdir(exist_ok=True)
PRIVATE_HISTORY.mkdir(exist_ok=True)

GROUP_LIST_FILE: Path = HISTORY_DIR / "group_list.json"
group_list = history_mgr.read_json(str(GROUP_LIST_FILE))

bot = BotClient()

# ========== 注册命令 ===========
"""###### 已转移 #####"""
# ========= 注册命令路由 ==========
"""###### 已转移 ######"""
# ========== 解析命令 ===========
COMMAND_NOT_FOUND = -255
# 不受模块开关影响的命令：避免 /module disable 把自己锁死后无法再启用
UNGUARDED_COMMANDS = frozenset({"/module"})


async def find_command(command):
    try:
        tokens = shlex.split(command)
        command_name = tokens[0]
        command_args = tokens[1:]
        route = command_route
        if command_name == "/manager" or command_name == "/mg":
            route = command_manager_map
            command_name = command_args[0]
            command_args = command_args[1:]
        
        if command_name in route:
            if (
                command_name not in UNGUARDED_COMMANDS
                and not mm.is_command_enabled(command_name)
            ):
                owner = mm.command_owner.get(command_name, "未知模块")
                if owner not in mm.modules:
                    # 模块导入失败时命令可能已注册，此时它根本没被加载过，不是"被禁用"
                    return (
                        f"命令 {command_name} 所属模块 {owner} 未成功加载，"
                        f"请查看启动日志里的 [tools] 报错"
                    )
                return (
                    f"命令 {command_name} 所在模块 {owner} 已被禁用，"
                    f"可用 /module enable {owner} 重新开启"
                )
            # command_args = " ".join(command_args).strip()
            func = route[command_name]
            sig = inspect.signature(func)
            len_params = len(sig.parameters)
            if len_params == 1:
                command_args = " ".join(command_args).strip()
            else:
                command_args = command_args[:len_params]

            # 关键：异步函数若被同步装饰器包过（例如 async def 配 @require_role），
            # iscoroutinefunction 会返回 False，调用结果是一个没人 await 的协程，
            # 表现为「命令有反应但不返回内容」。这里统一兜底 await。
            if inspect.iscoroutinefunction(func):
                ret = await func(command_args) if isinstance(command_args, str) else await func(*command_args)
            else:
                ret = func(command_args) if isinstance(command_args, str) else func(*command_args)
                if inspect.isawaitable(ret):
                    ret = await ret
            return ret if ret else None
        else:
            return COMMAND_NOT_FOUND
    except TypeError as e:
        return f"参数错误: {str(e)}"
    except Exception as e:
        print(-255)
        print(e)
        return COMMAND_NOT_FOUND



async def send_qc(text: str) -> str:
    """
    接受标准CQ码，例如：
    [CQ:at,qq=100000002] 这是一条AT消息
    当需要使用CQ码，时请调用此工具
    """
    BOT = context.get_bot()
    CHAT_TYPE = context.get_chat_type()
    CHAT_ID = context.get_chat_id()
    response = MessageArray.from_list(parse_cq_code_to_onebot11(text))
    if CHAT_TYPE == 0:  # group
        ret = await BOT.api.qq.post_group_array_msg(group_id=CHAT_ID, msg=response)
        return ret
    elif CHAT_TYPE == 1:  # private
        ret = await BOT.api.qq.post_private_array_msg(user_id=CHAT_ID, msg=response)
        return ret

# ========== 程序入口 ===========
_started = False


async def _lazy_start():
    global _started
    if _started:
        return
    _started = True
    # 绑定主动推送（后台任务/定时任务都通过 aullbot.push 发消息）
    push.bind(bot)
    from aullbot.tools import _pending_registers
    for reg in _pending_registers:
        try:
            reg(bot)
        except Exception as e:
            print(f"[main] 模块 register 失败: {e}")
    await mm.load_all(bot)


@bot.on_startup()
async def _on_startup():
    """进程启动即初始化模块后台任务（如 B站推送），不再依赖第一条消息。"""
    print("[main] 启动完成，初始化模块后台任务")
    try:
        await _lazy_start()
    except Exception as e:
        print(f"[main] 启动初始化失败: {type(e).__name__}: {e}")


"""群聊"""
group_message_queue = {}
@registrar.qq.on_group_message(priority=100)
async def is_group_me(event: GroupMessageEvent):
    group_id = str(event.group_id)
    group_message_queue.setdefault(group_id, [0, 0, 0])
    if not group_message_queue[group_id]:
        group_message_queue[group_id] = [0, 0, 0]

    if history_mgr.chat_exists(event.group_id, TYPE_GROUP):
        pass
    else:
        history_mgr.add_chat_list(event.group_id, TYPE_GROUP)
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

    context.set_context(
        bot,
        TYPE_GROUP,
        event.group_id,
        cache_path=str(CACHE_DIR),
        user_role=event.sender.role,
        sender_id=event.sender.user_id,
        raw_message=msg_text,
    )

    if msg_text == "撤回":
        if group_message_queue[event.group_id][-1] == 0:
            msg_result = await bot.api.qq.post_group_msg(
                group_id=event.group_id, text="没发消息你撤回什么"
            )
            group_message_queue[event.group_id].append(msg_result["message_id"])
            group_message_queue[event.group_id].pop(0)
            return
        await bot.api.qq.messaging.delete_msg(group_message_queue[event.group_id][-1])
        group_message_queue[event.group_id].pop(-1)
        group_message_queue[event.group_id].insert(0, 0)
        return
    text_to_send = await find_command(command=msg_text)
    # 只有 -255 才是"没命中命令"；None/"" 表示命令已处理（自己发过消息），
    # 不能再落到 AI 分支，否则 /img、/music 这类会二次触发模型
    if text_to_send != COMMAND_NOT_FOUND:
        if isinstance(text_to_send, str) and text_to_send:
            print(f"[Sysetm] 待发送:{text_to_send}")
            msg_result = await bot.api.qq.post_group_msg(
                group_id=event.group_id, text=text_to_send
            )
            group_message_queue[event.group_id].append(msg_result["message_id"])
            group_message_queue[event.group_id].pop(0)
        return
    if any(
        isinstance(seg, At) and str(seg.user_id) == str(self_id)
        for seg in event.message
    ):
        print("call ai")
        msg_result = await ai_chat_main(
            chat_id=event.group_id,
            metadata=set_metadata(qq_number, nickname, msg_text, "group"),
            callback=send_qc,
            chat_type=0,
        )
        if isinstance(msg_result, str):
            msg_no_permission = await bot.api.qq.post_group_msg(group_id=event.group_id, text=msg_result)
            group_message_queue[event.group_id].append(msg_no_permission["message_id"])
        else:
            group_message_queue[event.group_id].append(msg_result["message_id"])
        group_message_queue[event.group_id].pop(0)
    await _lazy_start()


"""私聊"""
@registrar.on_private_message(priority=100)
async def is_private_me(event: PrivateMessageEvent):

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
    
    context.set_context(
        bot,
        TYPE_PRTVATE,
        event.user_id,
        cache_path=str(CACHE_DIR),
        user_role="owner",
        sender_id=event.user_id,
        raw_message=msg_text,
    )

    text_to_send = await find_command(command=msg_text)
    if isinstance(text_to_send, str) and text_to_send:
        print(f"\n{text_to_send}")
        await event.reply(text=text_to_send, at_sender=False)
    elif text_to_send == COMMAND_NOT_FOUND:
        print("[System] Calling ai")
        msg_result = await ai_chat_main(
            chat_id=event.user_id,
            metadata=set_metadata(qq_number, nickname, msg_text, "private"),
            callback=send_qc,
            chat_type=1,
        )
        if isinstance(msg_result, str):
            await bot.api.qq.post_private_msg(user_id=event.user_id, text=msg_result)
    await _lazy_start()


# =========== 调用 ============

if __name__ == "__main__":
    bot.run()

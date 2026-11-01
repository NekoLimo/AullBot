# src/aullbot/push.py
"""主动推送（框架层接口）。

后台任务、定时任务、跨模块通知都不在「某个用户消息」的上下文里，
不能依赖 context / event.reply，统一走这里。

用法::

    from aullbot import push

    push.bind(bot)                                   # 启动时绑定一次（main 里做）
    await push.send_group(group_id, "文本")
    await push.send_private(user_id, "文本")
    await push.send(chat_type, chat_id, "文本")        # 0=群 1=私聊
    await push.send_many([("group", 123), ("private", 456)], "文本")
    await push.send_forward(0, 123, [("标题", "正文"), ...])

约定：
  * 永不抛异常，失败返回 False（send_many 返回成功条数），调用方自己决定是否重试
  * 失败原因打到 stdout，带异常类型
  * 目标会话去重、保序；批量发送之间留 gap，避免触发风控/刷屏
"""
import asyncio
from typing import Any, Iterable

_BOT: Any = None
DEFAULT_GAP = 0.3


def bind(bot) -> None:
    """绑定 BotClient。在 bot 启动流程里调用一次。"""
    global _BOT
    _BOT = bot


def is_bound() -> bool:
    return _BOT is not None


def _api():
    if _BOT is None:
        return None
    try:
        return _BOT.api.qq
    except Exception:
        return None


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def send_group(group_id, text: str) -> bool:
    """向群发送纯文本。"""
    api = _api()
    if api is None:
        print("[push] 未绑定 bot，发送失败")
        return False
    gid = _to_int(group_id)
    if gid is None:
        print(f"[push] 群号非法: {group_id!r}")
        return False
    try:
        await api.post_group_msg(group_id=gid, text=text)
        return True
    except Exception as e:
        print(f"[push] 群 {gid} 发送失败: {type(e).__name__}: {e}")
        return False


async def send_private(user_id, text: str) -> bool:
    """向私聊发送纯文本。"""
    api = _api()
    if api is None:
        print("[push] 未绑定 bot，发送失败")
        return False
    uid = _to_int(user_id)
    if uid is None:
        print(f"[push] QQ 号非法: {user_id!r}")
        return False
    try:
        await api.post_private_msg(user_id=uid, text=text)
        return True
    except Exception as e:
        print(f"[push] 私聊 {uid} 发送失败: {type(e).__name__}: {e}")
        return False


async def send_record(chat_type: int, chat_id, file: str) -> bool:
    """发送语音（file 支持本地路径/URL）。"""
    api = _api()
    if api is None:
        print("[push] 未绑定 bot，语音发送失败")
        return False
    cid = _to_int(chat_id)
    if cid is None:
        print(f"[push] 会话号非法: {chat_id!r}")
        return False
    try:
        if int(chat_type) == 0:
            await api.send_group_record(group_id=cid, file=file)
        else:
            await api.send_private_record(user_id=cid, file=file)
        return True
    except Exception as e:
        print(f"[push] 语音发送失败 {chat_type}/{cid}: {type(e).__name__}: {e}")
        return False


async def send(chat_type: int, chat_id, text: str) -> bool:
    """按会话类型发送：0=群，1=私聊。"""
    if int(chat_type) == 0:
        return await send_group(chat_id, text)
    return await send_private(chat_id, text)


async def send_many(targets: Iterable[tuple[str, Any]], text: str,
                    gap: float = DEFAULT_GAP) -> int:
    """批量推送，返回成功条数。

    targets: [("group", 群号), ("private", QQ号)]，自动去重保序。
    """
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, Any]] = []
    for kind, chat_id in targets:
        key = (str(kind), str(chat_id))
        if key in seen:
            continue
        seen.add(key)
        ordered.append((kind, chat_id))

    ok = 0
    for index, (kind, chat_id) in enumerate(ordered):
        sent = await send(0 if kind == "group" else 1, chat_id, text)
        if sent:
            ok += 1
        if gap and index < len(ordered) - 1:
            await asyncio.sleep(gap)
    return ok


async def send_forward(chat_type: int, chat_id,
                       blocks: list[tuple[str, str]],
                       nickname: str = "通知",
                       sender_id: str | int = "0") -> bool:
    """合并转发发送，blocks 为 [(标题, 正文)]，每条一个节点。"""
    api = _api()
    if api is None:
        print("[push] 未绑定 bot，合并转发失败")
        return False
    if not blocks:
        return False

    from ncatbot.types import PlainText
    from ncatbot.types.qq import Forward, ForwardNode

    try:
        nodes = [
            ForwardNode(user_id=str(sender_id), nickname=nickname,
                        content=[PlainText(text=f"{title}\n{body}".strip())])
            for title, body in blocks
        ]
        forward = Forward(content=nodes)
        cid = _to_int(chat_id)
        if cid is None:
            print(f"[push] 会话号非法: {chat_id!r}")
            return False
        if int(chat_type) == 0:
            await api.post_group_forward_msg(cid, forward)
        else:
            await api.post_private_forward_msg(cid, forward)
        return True
    except Exception as e:
        print(f"[push] 合并转发失败: {type(e).__name__}: {e}")
        return False

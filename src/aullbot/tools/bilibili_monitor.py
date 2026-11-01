# src/aullbot/tools/bilibili_monitor.py
"""B站 UP 主 动态 / 投稿 监控推送（bpi-py）。

设计要点（均按 2026-10 实测校准）
--------------------------------
* **动态为主、投稿兜底**：投稿发布后会立刻生成一条 ARCHIVE 动态，所以动态
  接口最快；投稿列表（arc/search）有 2 分钟以上延迟，只每 N 轮查一次兜底，
  用来覆盖「关闭同步动态」的 UP。
* 解析看 `modules.module_dynamic.major.type`，不是 `type_field`（实测两者不一致）；
  `opus.summary` 可能是富文本对象，必须强制转字符串。
* 已见内容按 id 集合持久化，重启不重复推送；集合按数量截断。
* 推送失败不推进状态，下一轮重试；单个 uid 失败只推迟它自己。
* UA 必须覆盖：bpi 默认 `Mozilla/5.0` 会被 WAF 直接 412。
* 默认 45 秒一轮；实测 25 秒 ≈2.4 请求/分钟安全，10 秒以下必然 -352。
"""
import asyncio
import json
import os
import random
import re
from pathlib import Path

from aullbot.module_meta import ModuleMeta
from aullbot.command_registry import command, ai_tools
from aullbot.rbac import require_role_async
from aullbot.module_manager import mm
from aullbot import context
from aullbot import push
from pydantic import TypeAdapter

MODULE = ModuleMeta(
    name="bilibili_monitor",
    author="Limo",
    description="B站 UP主 动态/投稿 更新监控（bpi-py）",
    version="0.4.0",
    default_enabled=True,
    tags=("api", "bilibili", "monitor"),
    config_schema={
        "interval": {
            "type": "int",
            "default": 45,
            "desc": "轮询间隔（秒），30~3600，默认 45",
        },
        "include_dynamic": {"type": "bool", "default": True, "desc": "是否监控动态"},
        "include_video": {
            "type": "bool",
            "default": True,
            "desc": "是否监控投稿列表（兜底，慢）",
        },
        "video_every": {
            "type": "int",
            "default": 1,
            "desc": "每 N 轮查一次投稿列表（1=每轮，保证 1 分钟内推送）",
        },
    },
    readme="""
命令：
  /bili-sub <uid>     订阅 B站 UP主（动态 + 投稿）
  /bili-unsub <uid>   取消订阅
  /bili-list          查看本会话订阅的 UP主
  /bili-check         立即检查本会话订阅的 UP（管理员，排障用）
  /bili-sync          对齐基线：拉本群订阅的 UP 最新 5 动态+5 投稿并记为已知
                      （管理员；合并转发发送，只影响当前会话）

工作方式：
  动态接口每轮都查（最快，发投稿会立刻生成一条 ARCHIVE 动态）。
  投稿列表每 video_every 轮查一次兜底（arc/search 有 2 分钟以上延迟）。

配置（bot_data/modules.json）：
  {
    "bilibili_monitor": {
      "config": {
        "interval": 45,
        "include_dynamic": true,
        "include_video": true,
        "video_every": 1
      }
    }
  }
  interval 限制在 30~3600 秒。实测 10 秒以下必然被风控（-352）。

认证（.env 或环境变量）：
  BILI_SESSDATA / BILI_JCT / BILI_DEDEUSERID / BILI_BUVID3 / BILI_BUVID4
  推荐扫码获取，不要手工复制。

首次订阅只记基线，不推送历史内容；推送全失败时不推进状态，下一轮重试。
""",
)

# 绝对路径：换目录启动不会"订阅清空"
BOT_DATA = Path(__file__).resolve().parents[3] / "bot_data"
SUB_PATH = BOT_DATA / "bilibili_subs.json"
STATE_PATH = BOT_DATA / "bilibili_state.json"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_INTERVAL = 45
MIN_INTERVAL = 30
MAX_INTERVAL = 3600
VIDEO_EVERY = 1
STATE_LIMIT = 300
MAX_BACKOFF_SHIFT = 6
MIN_BACKOFF = 60
MAX_ITEMS_PER_MSG = 3

# 空间动态：/feed/all 是「关注动态」，未关注的 UP 会返回 0，
# 必须用 /feed/space 才能查任意 UP 的动态
SPACE_FEED_PATH = "/x/polymer/web-dynamic/v1/feed/space"
_SPACE_ADAPTER = TypeAdapter(dict)

_TICK_LOCK = asyncio.Lock()
_ROUND = 0
_warned: set[str] = set()


def _warn_once(key: str, msg: str) -> None:
    if key not in _warned:
        _warned.add(key)
        print(msg)


# ==================== 订阅与状态读写 ====================

def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[bili] 读取 {path.name} 失败（按空处理）: {type(e).__name__}: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_subs() -> dict:
    data = _load_json(SUB_PATH)
    data.setdefault("group", {})
    data.setdefault("private", {})
    return data


def _save_subs(data: dict) -> None:
    _save_json(SUB_PATH, data)


def _load_state() -> dict:
    return _load_json(STATE_PATH)


def _save_state(state: dict) -> None:
    _save_json(STATE_PATH, state)


def _kind() -> str:
    return "group" if context.get_chat_type() == 0 else "private"


def _known_sets(cur: dict) -> tuple[set[str], set[str]]:
    """兼容旧状态格式（video/dynamic 曾存单个字符串）。"""
    def to_set(value) -> set[str]:
        if isinstance(value, str):
            return {value} if value else set()
        if isinstance(value, list):
            return {str(x) for x in value if x}
        return set()

    return to_set(cur.get("dynamic")), to_set(cur.get("video"))


def _trim(ids: set[str]) -> list[str]:
    return sorted(ids, reverse=True)[:STATE_LIMIT]


# ==================== 命令 ====================

def _valid_uid(uid: str) -> bool:
    # 只接受 ASCII 数字且不以 0 开头：isdigit() 会放过全角数字，
    # int() 还会因为 "²" 这类字符抛 ValueError。16 位 MID 是合法的。
    return bool(re.fullmatch(r"[1-9][0-9]{0,19}", uid))


@command("/bili-sub")
@require_role_async("user")
async def bili_sub(uid: str) -> str:
    """订阅 B站 UP主：/bili-sub <uid>"""
    uid = (uid or "").strip()
    if not _valid_uid(uid):
        return "UID 必须是合法数字"
    data = _load_subs()
    kind = _kind()
    chat_id = str(context.get_chat_id())
    lst = data[kind].setdefault(chat_id, [])
    if uid in lst:
        return f"本会话已订阅 {uid}"
    lst.append(uid)
    _save_subs(data)
    return f"已订阅 UP主 {uid}，下次更新时推送"


@command("/bili-unsub")
@require_role_async("user")
async def bili_unsub(uid: str) -> str:
    """取消订阅：/bili-unsub <uid>"""
    uid = (uid or "").strip()
    if not _valid_uid(uid):
        return "UID 必须是合法数字"
    data = _load_subs()
    kind = _kind()
    chat_id = str(context.get_chat_id())
    lst = data[kind].get(chat_id, [])
    if uid not in lst:
        return f"本会话未订阅 {uid}"
    lst.remove(uid)
    if not lst:
        data[kind].pop(chat_id, None)
    _save_subs(data)
    return f"已取消订阅 {uid}"


@command("/bili-list")
@require_role_async("user")
async def bili_list(args: str = "") -> str:
    """查看本会话订阅的 UP主：/bili-list"""
    lst = _load_subs()[_kind()].get(str(context.get_chat_id()), [])
    if not lst:
        return "本会话没有订阅任何 UP主"
    return "本会话订阅：\n" + "\n".join(lst)


@command("/bili-check")
@require_role_async("admin")
async def bili_check(args: str = "") -> str:
    """立即检查本会话订阅的 UP，返回本轮统计：/bili-check"""
    kind = _kind()
    uids = _load_subs()[kind].get(str(context.get_chat_id()), [])
    if not uids:
        return "本会话没有订阅任何 UP主"

    bot = context.get_bot()
    checked, errors, pushed = await _tick(bot, _cfg(), force_video=True,
                                          only_uids=list(uids))
    return (f"本会话检查：成功 {checked}、失败 {errors}、推送 {pushed} 条"
            f"（共 {len(uids)} 个 UP）")


SYNC_SHOW = 5          # 每类展示条数
SYNC_FALLBACK_LEN = 1600


async def _sync_uids(uids: list[str]) -> tuple[list[tuple[str, str]], int]:
    """拉取这些 uid 的最近动态/投稿各 5 条，并把它们对齐为基线。

    只用当前会话的订阅，不影响其它群。返回 ([(标题, 正文)], 失败接口数)。
    """
    async with _TICK_LOCK:
        try:
            client = _build_client()
        except Exception as e:
            print(f"[bili] sync 客户端创建失败: {_explain(e)}")
            return [], 1

        state = _load_state()
        blocks: list[tuple[str, str]] = []
        total_failures = 0
        try:
            for uid in uids:
                try:
                    num = int(uid)
                except (TypeError, ValueError):
                    continue
                dynamics, videos, failures, dyn_ok, vid_ok = await _fetch(
                    client, num, want_video=True
                )
                total_failures += failures

                cur = state.setdefault(str(uid), {})
                known_dyn, known_vid = _known_sets(cur)

                # 对齐基线：当前内容全部记为已知，水位线推到最新
                if dyn_ok:
                    known_dyn.update(_dyn_id(x) for x in dynamics if _dyn_id(x))
                    cur["dyn_wm"] = max(
                        [float(cur.get("dyn_wm") or 0)] + [_dyn_ts(x) for x in dynamics]
                    )
                    cur["dyn_ready"] = True
                if vid_ok:
                    known_vid.update(_video_id(v) for v in videos if _video_id(v))
                    cur["vid_wm"] = max(
                        [float(cur.get("vid_wm") or 0)] + [_video_ts(v) for v in videos]
                    )
                    cur["vid_ready"] = True
                known_vid.update(_dyn_bvid(x) for x in dynamics if _dyn_bvid(x))
                cur["dynamic"] = _trim(known_dyn)
                cur["video"] = _trim(known_vid)

                title = f"UP {uid}｜动态 {len(dynamics)} 条 / 投稿 {len(videos)} 条"
                lines: list[str] = []
                if not dyn_ok:
                    lines.append("动态：拉取失败")
                else:
                    lines.append(f"【动态最新 {min(SYNC_SHOW, len(dynamics))} 条】")
                    for item in dynamics[:SYNC_SHOW]:
                        text = _clip(_dyn_text(item), 40) or "（无正文）"
                        lines.append(f"· {_dyn_time_text(item)} {text}")
                        lines.append(f"  {_dyn_link(item)}")
                    if not dynamics:
                        lines.append("· （没有动态）")
                lines.append("")
                if not vid_ok:
                    lines.append("投稿：拉取失败")
                else:
                    lines.append(f"【投稿最新 {min(SYNC_SHOW, len(videos))} 条】")
                    for video in videos[:SYNC_SHOW]:
                        lines.append(f"· {_clip(_get_attr(video, 'title', ''), 40)}")
                        lines.append(
                            f"  https://www.bilibili.com/video/{_video_id(video)}")
                    if not videos:
                        lines.append("· （没有投稿）")
                blocks.append((title, "\n".join(lines)))
        finally:
            try:
                await client.aclose()
            except Exception:
                pass

        _save_state(state)

    return blocks, total_failures


@command("/bili-sync")
@require_role_async("admin")
async def bili_sync(args: str = "") -> str:
    """对齐基线：拉取本会话订阅的 UP 最新 5 条动态 + 5 条投稿并记为已知"""
    kind = _kind()
    chat_id = str(context.get_chat_id())
    uids = _load_subs()[kind].get(chat_id, [])
    if not uids:
        return "本会话没有订阅任何 UP主"

    blocks, failures = await _sync_uids(list(uids))
    if not blocks:
        return "同步失败：一个 UP 都没拉到数据" + ("（被限流？）" if failures else "")

    sent = await push.send_forward(
        context.get_chat_type(),
        context.get_chat_id(),
        blocks,
        nickname="B站同步",
        sender_id=context.get_sender_id() or "0",
    )

    tail = f"（{failures} 个接口失败）" if failures else ""
    if sent:
        return f"已对齐基线：{len(blocks)} 个 UP{tail}，详情见上面的合并转发"

    # 合并转发失败时退回文本，至少能看到内容
    flat = "\n\n".join(f"{title}\n{body}" for title, body in blocks)
    head = f"合并转发失败，退回文本（已对齐基线{tail}）：\n\n"
    if len(head) + len(flat) > SYNC_FALLBACK_LEN:
        flat = flat[: SYNC_FALLBACK_LEN - len(head) - 1] + "…"
    return head + flat


# ==================== AI 工具 ====================

@ai_tools("bili_subscribe")
@require_role_async("user")
async def bili_subscribe_tool(uid: str) -> str:
    """订阅 B站 UP 主更新，参数 uid 为数字 UID"""
    return await bili_sub(uid)


@ai_tools("bili_unsubscribe")
@require_role_async("user")
async def bili_unsubscribe_tool(uid: str) -> str:
    """取消订阅 B站 UP 主更新，参数 uid"""
    return await bili_unsub(uid)


@ai_tools("bili_list")
@require_role_async("user")
async def bili_list_tool() -> str:
    """列出本会话订阅的 B站 UP 主"""
    return await bili_list()


# ==================== 配置 ====================

def _cfg() -> dict:
    """config_schema 的 default 打底，modules.json 里的值覆盖。"""
    cfg: dict = {}
    for key, spec in (MODULE.config_schema or {}).items():
        if isinstance(spec, dict) and "default" in spec:
            cfg[key] = spec["default"]
    mod = mm.modules.get(MODULE.name)
    if mod is not None and isinstance(mod.config, dict):
        cfg.update(mod.config)
    return cfg


def _clamp_int(raw, default: int, low: int, high: int, tag: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        _warn_once(f"{tag}_bad", f"[bili] {tag}={raw!r} 非法，回退 {default}")
        return default
    if value < low:
        _warn_once(f"{tag}_low", f"[bili] {tag}={value} 过小，按 {low} 处理")
        return low
    if value > high:
        _warn_once(f"{tag}_high", f"[bili] {tag}={value} 过大，按 {high} 处理")
        return high
    return value


def _interval(cfg: dict) -> int:
    return _clamp_int(cfg.get("interval", DEFAULT_INTERVAL), DEFAULT_INTERVAL,
                      MIN_INTERVAL, MAX_INTERVAL, "interval")


def _video_every(cfg: dict) -> int:
    return _clamp_int(cfg.get("video_every", VIDEO_EVERY), VIDEO_EVERY, 1, 100, "video_every")


# ==================== 客户端 ====================

def _cookie() -> str | None:
    pairs = []
    for env, name in (("BILI_SESSDATA", "SESSDATA"), ("BILI_JCT", "bili_jct"),
                      ("BILI_DEDEUSERID", "DedeUserID"), ("BILI_BUVID3", "buvid3"),
                      ("BILI_BUVID4", "buvid4")):
        value = os.environ.get(env, "").strip()
        if value:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs) or None


def _build_client():
    """创建 AsyncBpiClient，并覆盖 WAF 敏感的 UA。"""
    import bpi.client as bpi_client
    from bpi import AsyncBpiClient

    bpi_client.HEADERS["user-agent"] = BROWSER_UA

    kwargs: dict = {"trust_env": False}  # 避免 shell 里的代理变量带来机房 IP
    cookie = _cookie()
    if cookie:
        kwargs["cookie"] = cookie
    return AsyncBpiClient(**kwargs)


# ==================== 解析 ====================

def _get_attr(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _dig(obj, *keys, default=None):
    cur = obj
    for key in keys:
        cur = _get_attr(cur, key, None)
        if cur is None:
            return default
    return cur if cur is not None else default


def _as_text(value) -> str:
    """把可能是富文本对象的字段统一成字符串（实测 opus.summary 就是对象）。"""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "summary", "title", "content"):
            inner = value.get(key)
            if isinstance(inner, str) and inner:
                return inner
        return ""
    return "" if value is None else str(value)


def _dyn_major_type(item) -> str:
    return str(_dig(item, "modules", "module_dynamic", "major", "type", default=""))


def _dyn_id(item) -> str:
    return str(_dig(item, "id_str", default="") or "")


def _dyn_ts(item) -> int:
    try:
        return int(_dig(item, "modules", "module_author", "pub_ts", default=0))
    except (TypeError, ValueError):
        return 0


def _dyn_author(item) -> str:
    return str(_dig(item, "modules", "module_author", "name", default="?"))


def _dyn_time_text(item) -> str:
    return str(_dig(item, "modules", "module_author", "pub_time", default=""))


def _dyn_text(item) -> str:
    md = _dig(item, "modules", "module_dynamic", default=None) or {}
    text = _as_text(_dig(md, "desc", "text", default=""))
    if text:
        return text
    for path in (("major", "opus", "title"), ("major", "opus", "summary"),
                 ("major", "archive", "title"), ("major", "article", "title"),
                 ("major", "live_rcmd", "title"), ("major", "common", "title")):
        value = _as_text(_dig(md, *path, default=""))
        if value:
            return value
    items = _dig(md, "major", "draw", "items", default=None)
    if isinstance(items, list):
        for one in items:
            desc = _as_text(_get_attr(one, "desc", ""))
            if desc:
                return desc
    # 转发动态：自己没写正文时取被转发的那条
    orig = _get_attr(item, "orig", None)
    if orig:
        orig_md = _dig(orig, "modules", "module_dynamic", default=None) or {}
        text = _as_text(_dig(orig_md, "desc", "text", default=""))
        if not text:
            for path in (("major", "opus", "title"), ("major", "archive", "title"),
                         ("major", "opus", "summary")):
                text = _as_text(_dig(orig_md, *path, default=""))
                if text:
                    break
        if text:
            return f"转发：{text}"
    return ""


def _dyn_images(item) -> list[str]:
    md = _dig(item, "modules", "module_dynamic", default=None) or {}
    urls: list[str] = []
    for one in _dig(md, "major", "opus", "pics", default=None) or []:
        url = _as_text(_get_attr(one, "url", ""))
        if url:
            urls.append(url)
    for one in _dig(md, "major", "draw", "items", default=None) or []:
        url = _as_text(_get_attr(one, "src", ""))
        if url:
            urls.append(url)
    cover = _as_text(_dig(md, "major", "archive", "cover", default=""))
    if cover:
        urls.append(cover)
    return urls


def _dyn_bvid(item) -> str:
    """ARCHIVE 类型动态里带的投稿 bvid；用于和投稿列表去重。"""
    return _as_text(_dig(item, "modules", "module_dynamic", "major", "archive", "bvid",
                         default=""))


def _dyn_link(item) -> str:
    """ARCHIVE 类型直接给视频链接，其它给动态链接。"""
    bvid = _as_text(_dig(item, "modules", "module_dynamic", "major", "archive", "bvid",
                         default=""))
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    return f"https://t.bilibili.com/{_dyn_id(item)}"


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def _video_id(video) -> str:
    return str(_get_attr(video, "bvid", "") or "")


def _video_ts(video) -> int:
    try:
        return int(_get_attr(video, "created", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _pick_fresh(items: list, id_of, ts_of, known: set[str], watermark: float) -> list:
    """挑出真正的新增：既没记录过，又不比已知最新更老。

    动态接口返回的条数会浮动（12 → 16），只按 id 判断会把更早的历史
    当成新增推出去，所以必须加时间水位线。
    """
    fresh = []
    for item in items:
        ident = id_of(item)
        if not ident or ident in known:
            continue
        ts = ts_of(item)
        if watermark and ts and ts < watermark:
            continue
        fresh.append(item)
    fresh.sort(key=ts_of)
    return fresh


# ==================== 拉取 ====================

async def _fetch_dynamics(client, uid: int) -> list:
    """拉某个 UP 的空间动态（含转发/视频/图文等全部类型）。

    注意：不能用 dynamic.all（那是「关注动态」，未关注的人返回空）。
    _get_payload 会走 bpi 的 envelope，code!=0 时抛 ApiError、HTTP 异常也照常抛，
    失败才能被 _tick 计入退避。
    """
    data = await client._get_payload(
        SPACE_FEED_PATH,
        {"host_mid": str(uid), "offset": ""},
        _SPACE_ADAPTER,
    )
    return list((data or {}).get("items") or [])


async def _fetch(client, uid: int, want_video: bool):
    """返回 (动态列表, 投稿列表, 失败次数, 动态是否成功, 投稿是否成功)。"""
    dynamics: list = []
    videos: list = []
    failures = 0
    dyn_ok = vid_ok = False

    try:
        dynamics = await _fetch_dynamics(client, uid)
        dyn_ok = True
    except Exception as e:
        failures += 1
        print(f"[bili] {uid} 动态拉取失败: {_explain(e)}")

    if want_video:
        try:
            resp = await client.user.uploaded_videos(mid=uid, page_size=8)
            videos = list(getattr(getattr(resp, "list", None), "videos", None) or [])
            vid_ok = True
        except Exception as e:
            failures += 1
            print(f"[bili] {uid} 投稿拉取失败: {_explain(e)}")

    return dynamics, videos, failures, dyn_ok, vid_ok


def _explain(exc: Exception) -> str:
    name, text = type(exc).__name__, str(exc)
    if name == "HttpStatusError" and "412" in text:
        return "HTTP 412（UA/指纹被 WAF 拦）"
    if name == "ApiError" and "-352" in text:
        return "-352（风控限流，需要降频）"
    if name == "AuthenticationError" or "-101" in text:
        return "-101（未登录，cookie 失效或被降级成匿名）"
    low = text.lower()
    if name.endswith("Timeout") or "timeout" in low or "timed out" in low:
        return "超时"
    return f"{name}: {text}"


# ==================== 消息构造 ====================

def _fmt_dynamic(item) -> str:
    kind = _dyn_major_type(item).replace("MAJOR_TYPE_", "") or "动态"
    head = f"[{kind}] {_dyn_author(item)} {_dyn_time_text(item)}".strip()
    body = _clip(_dyn_text(item), 200) or "（无正文）"
    lines = [head, body]
    images = _dyn_images(item)
    if images:
        lines.append(f"（{len(images)} 张图）")
    lines.append(_dyn_link(item))
    return "\n".join(lines)


def _fmt_video(video) -> str:
    title = _clip(_get_attr(video, "title", ""), 80)
    return f"{title}\nhttps://www.bilibili.com/video/{_video_id(video)}"


def _compose(new_dyn: list, new_vid: list) -> str | None:
    sections: list[str] = []
    # 列表是升序（旧→新），只展示最新的几条：取尾部
    if new_dyn:
        shown = new_dyn[-MAX_ITEMS_PER_MSG:]
        parts = [f"【动态更新 ×{len(new_dyn)}】"]
        parts.extend(_fmt_dynamic(x) for x in shown)
        if len(new_dyn) > len(shown):
            parts.append(f"…另有 {len(new_dyn) - len(shown)} 条较早的未展示")
        sections.append("\n".join(parts))
    if new_vid:
        shown_v = new_vid[-MAX_ITEMS_PER_MSG:]
        parts_v = [f"【投稿更新 ×{len(new_vid)}】"]
        parts_v.extend(_fmt_video(v) for v in shown_v)
        if len(new_vid) > len(shown_v):
            parts_v.append(f"…另有 {len(new_vid) - len(shown_v)} 条较早的未展示")
        sections.append("\n".join(parts_v))
    if not sections:
        return None
    text = "\n\n".join(sections)
    return text if len(text) <= 1500 else text[:1500] + "…"


# ==================== 推送 ====================

def _all_uids(subs: dict) -> set[int]:
    uids: set[int] = set()
    for kind in ("group", "private"):
        for lst in subs[kind].values():
            for one in lst:
                try:
                    uids.add(int(one))
                except (TypeError, ValueError):
                    continue
    return uids


def _targets_of(subs: dict, uid: int) -> list[tuple[str, str]]:
    out = []
    for kind in ("group", "private"):
        for chat_id, lst in subs[kind].items():
            if str(uid) in lst:
                out.append((kind, chat_id))
    return out


async def _broadcast(bot, uid: int, text: str) -> int:
    """推送前重读订阅，避免推给刚退订的会话。统一走 aullbot.push。"""
    if bot is not None and not push.is_bound():
        push.bind(bot)  # 兜底：main 没绑定时用当前 bot
    targets = _targets_of(_load_subs(), uid)
    return await push.send_many(targets, text)


def _prune(state: dict, alive: set[int]) -> bool:
    alive_str = {str(a) for a in alive}
    dead = [u for u in list(state.keys()) if str(u) not in alive_str]
    for uid in dead:
        state.pop(uid, None)
    return bool(dead)


# ==================== 单轮 ====================

async def _tick(bot, cfg: dict, force_video: bool = False,
                only_uids: list[str] | None = None) -> tuple[int, int, int]:
    """跑一轮，返回 (成功 uid 数, 失败次数, 推送条数)。"""
    global _ROUND
    async with _TICK_LOCK:
        _ROUND += 1
        want_dyn = bool(cfg.get("include_dynamic", True))
        every = _video_every(cfg)
        want_video = bool(cfg.get("include_video", True)) and (
            force_video or _ROUND % every == 0
        )
        if not want_dyn and not want_video:
            return 0, 0, 0

        subs = _load_subs()
        # 传了 only_uids 就只处理这些（/bili-check 只查本会话，避免跨会话副作用）
        if only_uids is None:
            uids = _all_uids(subs)
        else:
            uids = {int(u) for u in only_uids if str(u).strip().isdigit()}
        state = _load_state()

        if not uids:
            if only_uids is None and _prune(state, set()):
                _save_state(state)
            return 0, 0, 0

        try:
            client = _build_client()
        except Exception as e:
            print(f"[bili] 客户端创建失败: {_explain(e)}")
            return 0, len(uids), 0

        checked = errors = pushed = 0
        dirty = False
        try:
            for uid in sorted(uids):
                cur = state.setdefault(str(uid), {})
                known_dyn, known_vid = _known_sets(cur)

                # 就绪标记：拉取成功即算（哪怕列表为空），
                # 否则「本来就没动态」的 UP 会每轮重建基线并吞掉第一条动态
                dyn_ready = bool(cur.get("dyn_ready")) or bool(known_dyn)
                vid_ready = bool(cur.get("vid_ready")) or bool(known_vid)
                # 必须在写入前判断：后面会把 dyn_wm/vid_wm 无条件写进 cur
                dyn_wm_missing = "dyn_wm" not in cur
                vid_wm_missing = "vid_wm" not in cur
                dyn_wm = float(cur.get("dyn_wm") or 0)
                vid_wm = float(cur.get("vid_wm") or 0)
                need_video = want_video or force_video or not vid_ready

                dynamics, videos, failures, dyn_ok, vid_ok = await _fetch(
                    client, uid, want_video=need_video
                )
                errors += failures

                empty = not dynamics and not videos
                if empty and failures == 0:
                    _warn_once(f"empty_{uid}", f"[bili] {uid} 本轮没有拿到任何数据")

                # 就绪标记必须先落，哪怕两边都是空的：
                # 0 动态 0 投稿的新账号若在这里 continue，将来第一条内容
                # 会被当成"基线"记入 known 而不推送（首条丢失）。
                just_baselined = False
                if dyn_ok and not dyn_ready:
                    known_dyn.update(_dyn_id(x) for x in dynamics if _dyn_id(x))
                    dyn_wm = max([dyn_wm] + [_dyn_ts(x) for x in dynamics])
                    cur["dyn_ready"] = True
                    just_baselined = True
                if vid_ok and not vid_ready:
                    known_vid.update(_video_id(v) for v in videos if _video_id(v))
                    vid_wm = max([vid_wm] + [_video_ts(v) for v in videos])
                    cur["vid_ready"] = True
                    just_baselined = True
                # 纯投稿动态里的 bvid 也算已知投稿，避免列表出现时再推一次
                known_vid.update(_dyn_bvid(x) for x in dynamics if _dyn_bvid(x))

                cur["dynamic"] = _trim(known_dyn)
                cur["video"] = _trim(known_vid)
                cur["dyn_wm"] = dyn_wm
                cur["vid_wm"] = vid_wm
                dirty = True

                if just_baselined:
                    print(f"[bili] {uid} 建立基线：动态 {len(known_dyn)} 条、"
                          f"投稿 {len(known_vid)} 条（不推送历史）")

                # 老状态没有水位线（升级前写的），先校准一次：把当前最新时间
                # 记为起点，本轮不推送，避免把窗口里更早的历史当新增
                dyn_cal = vid_cal = False
                # 用「键是否存在」判断是否已校准：水位线本身可能是 0
                # （该 UP 根本没有内容），用 not dyn_wm 会导致每轮重复校准
                if dyn_ok and dyn_ready and dyn_wm_missing:
                    dyn_wm = max([0.0] + [_dyn_ts(x) for x in dynamics])
                    cur["dyn_wm"] = dyn_wm
                    dyn_cal = True
                if vid_ok and vid_ready and vid_wm_missing and videos:
                    vid_wm = max([0.0] + [_video_ts(v) for v in videos])
                    cur["vid_wm"] = vid_wm
                    vid_cal = True
                if dyn_cal or vid_cal:
                    print(f"[bili] {uid} 校准时间水位线（动态 {dyn_wm:.0f} / 投稿 {vid_wm:.0f}）")

                checked += 1
                if empty:
                    continue

                new_dyn = ([] if (dyn_cal or not dyn_ready or not want_dyn)
                           else _pick_fresh(dynamics, _dyn_id, _dyn_ts, known_dyn, dyn_wm))
                new_vid = ([] if (vid_cal or not vid_ready)
                           else _pick_fresh(videos, _video_id, _video_ts, known_vid, vid_wm))

                if not new_dyn and not new_vid:
                    continue

                # 纯投稿动态（ARCHIVE，带 bvid）归到「投稿更新」里展示
                archived = [x for x in new_dyn if _dyn_bvid(x)]
                plain_dyn = [x for x in new_dyn if not _dyn_bvid(x)]
                as_videos = list(new_vid)
                seen_bv = {_video_id(v) for v in as_videos}
                for x in archived:
                    bv = _dyn_bvid(x)
                    if bv and bv not in seen_bv:
                        as_videos.append({
                            "bvid": bv,
                            "title": _clip(_dyn_text(x), 80),
                            "created": _dyn_ts(x),
                        })
                        seen_bv.add(bv)

                text = _compose(plain_dyn, as_videos)
                sent = await _broadcast(bot, uid, text) if text else 0
                if sent:
                    known_dyn.update(_dyn_id(x) for x in new_dyn)
                    known_vid.update(_video_id(v) for v in new_vid)
                    known_vid.update(_dyn_bvid(x) for x in new_dyn if _dyn_bvid(x))
                    if new_dyn:
                        dyn_wm = max(dyn_wm, max(_dyn_ts(x) for x in new_dyn))
                    if new_vid:
                        vid_wm = max(vid_wm, max(_video_ts(v) for v in new_vid))
                    cur["dynamic"] = _trim(known_dyn)
                    cur["video"] = _trim(known_vid)
                    cur["dyn_wm"] = dyn_wm
                    cur["vid_wm"] = vid_wm
                    dirty = True
                    pushed += sent
                    print(f"[bili] {uid} 推送 {sent} 个会话："
                          f"{len(new_dyn)} 动态 / {len(new_vid)} 投稿")
                else:
                    errors += 1
                    print(f"[bili] {uid} 推送全部失败，保留旧状态待下轮重试")
        finally:
            try:
                await client.aclose()
            except Exception as e:
                print(f"[bili] 关闭客户端失败: {type(e).__name__}: {e}")

        if only_uids is None and _prune(state, uids):
            dirty = True
        if dirty:
            _save_state(state)
        return checked, errors, pushed


# ==================== 轮询与生命周期 ====================

async def _loop(bot) -> None:
    if bot is None:
        print("[bili] 未拿到 bot 实例，监控未启动")
        return

    print("[bili] 监控已启动（bpi-py）")
    await asyncio.sleep(random.uniform(0.2, 1.0))  # 启动错峰

    backoff = 0
    while True:
        cfg = _cfg()
        interval = _interval(cfg)
        try:
            checked, errors, pushed = await _tick(bot, cfg)
            if errors == 0:
                backoff = 0
            else:
                backoff = min(backoff + 1, MAX_BACKOFF_SHIFT)
                print(f"[bili] 本轮 {errors} 个失败，退避 {backoff} 级")
        except asyncio.CancelledError:
            print("[bili] 监控已停止")
            raise
        except Exception as e:
            backoff = min(backoff + 1, MAX_BACKOFF_SHIFT)
            print(f"[bili] 轮询异常: {type(e).__name__}: {e}")

        if backoff:
            wait = max(interval * (2**backoff), MIN_BACKOFF * (2 ** (backoff - 1)))
        else:
            wait = interval
        wait = min(wait, MAX_INTERVAL)
        await asyncio.sleep(wait)


def register(bot):
    mod = mm.modules.get(MODULE.name)
    if mod is None:
        print("[bili] 模块未注册，跳过后台任务")
        return

    @mod.on_load
    async def _on_load(m, bot_):
        push.bind(bot_)
        print("[bili] 后台任务已注册")
        m.spawn(_loop(bot_))

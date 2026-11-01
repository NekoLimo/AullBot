#!/usr/bin/env python3
"""bilibili_monitor 完整回归测试（零依赖，不需要 pytest，不联网）。

运行：
    cd /root/AullBot
    ./.venv/bin/python -m tests.test_bilibili_monitor
    # 或
    ./.venv/bin/python tests/test_bilibili_monitor.py

覆盖：
  1  解析       五种动态形态 / 富文本 summary / 图片 / bvid / 链接
  2  消息构造   单条、多条、超量省略、长度上限
  3  基线       全新 uid 只记基线不推送
  4  按类型基线 旧格式 state（只有 video 单值）不会把动态历史推出去
  5  空 UP      本来没有动态的 UP：不重复建基线，且第一条动态能推
  6  水位线     接口返回条数变多（窗口滑动）不会把更老内容当新增
  7  迁移校准   老状态没有水位线时，首轮只校准不推送
  8  去重       动态里带的 bvid 与投稿列表不会推两次
  9  轮询门控   video_every 控制投稿查询频率
  10 推送失败   状态不推进，下一轮重试
  11 推送目标   只推给订阅了该 uid 的会话
  12 持久化     重启（重新加载状态）后不重复推送
  13 容错       状态文件损坏、接口失败
  14 配置       interval / video_every 的钳制与非法值
  15 uid 校验   16 位 MID 合法，全角数字/上标/前导零非法
  16 配置兜底   load_config 在文件缺失/损坏时返回 {}
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from aullbot.tools import bilibili_monitor as bm  # noqa: E402

PASS = 0
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name}  {detail}")
        print(f"  ✗ {name}  {detail}")


# ----------------------------------------------------------------- 夹具
def dyn(id_: str, text: str = "", ts: int = 1000, *, major: str = "MAJOR_TYPE_NONE",
        extra_major: dict | None = None, author: str = "UP") -> dict:
    major_obj = {"type": major}
    if extra_major:
        major_obj.update(extra_major)
    return {
        "id_str": id_,
        "modules": {
            "module_author": {"name": author, "pub_ts": str(ts), "pub_time": "刚刚"},
            "module_dynamic": {
                "desc": {"text": text} if text else None,
                "major": major_obj,
            },
        },
    }


def opus(id_: str, summary: str, ts: int = 1000, pics: int = 1) -> dict:
    return dyn(id_, "", ts, major="MAJOR_TYPE_OPUS", extra_major={
        "opus": {"title": "", "summary": {"text": summary, "rich_text_nodes": []},
                 "pics": [{"url": f"http://i0/pic{i}.jpg"} for i in range(pics)]},
    })


def archive(id_: str, bvid: str, title: str, ts: int = 1000) -> dict:
    return dyn(id_, "", ts, major="MAJOR_TYPE_ARCHIVE", extra_major={
        "archive": {"bvid": bvid, "title": title, "cover": "http://i2/cover.jpg"},
    })


def video(bvid: str, title: str, created: int = 1000):
    return SimpleNamespace(bvid=bvid, title=title, created=created, play=1)


# ----------------------------------------------------------------- 假环境
class FakeClient:
    """模拟 bpi 客户端。动态走 _get_payload（feed/space），投稿走 user.uploaded_videos。"""

    def __init__(self, state):
        self.s = state
        self.user = SimpleNamespace(uploaded_videos=self._vid)

    async def _get_payload(self, path, params, adapter, **kwargs):
        self.s["calls"].append(("dynamic", params.get("host_mid")))
        self.s["paths"].append(path)
        if self.s["dyn_exc"]:
            raise self.s["dyn_exc"]
        return {"items": list(self.s["dyn"]), "has_more": False}

    async def _vid(self, mid=None, page_size=None):
        self.s["calls"].append(("video", mid))
        if self.s["vid_exc"]:
            raise self.s["vid_exc"]
        return SimpleNamespace(list=SimpleNamespace(videos=list(self.s["vid"])))

    async def aclose(self):
        pass


class FakeQQ:
    def __init__(self, state):
        self.s = state

    async def post_group_msg(self, group_id=None, text=None):
        if self.s["push_exc"]:
            raise RuntimeError("禁言")
        self.s["sent"].append(("group", str(group_id), text))

    async def post_private_msg(self, user_id=None, text=None):
        if self.s["push_exc"]:
            raise RuntimeError("禁言")
        self.s["sent"].append(("private", str(user_id), text))


def make_env(tmp: Path):
    s = {"dyn": [], "vid": [], "dyn_exc": None, "vid_exc": None,
         "push_exc": False, "sent": [], "calls": [], "paths": []}
    bm.SUB_PATH = tmp / "subs.json"
    bm.STATE_PATH = tmp / "state.json"
    bm._ROUND = 0
    bm._warned.clear()
    bm._build_client = lambda: FakeClient(s)
    bot = SimpleNamespace(api=SimpleNamespace(qq=FakeQQ(s)))
    return s, bot


def subs(group: dict):
    bm._save_subs({"group": {str(k): v for k, v in group.items()}, "private": {}})


# ----------------------------------------------------------------- 1 解析
def test_parse() -> None:
    print("\n[1] 解析")
    check("OPUS 从 summary 取正文（富文本对象）",
          bm._dyn_text(opus("1", "富文本正文")) == "富文本正文",
          repr(bm._dyn_text(opus("1", "富文本正文"))))
    check("ARCHIVE 从投稿标题取正文",
          bm._dyn_text(archive("2", "BV1x", "视频标题")) == "视频标题")
    check("纯文字动态用 desc.text",
          bm._dyn_text(dyn("3", "纯文字")) == "纯文字")

    # 图文动态：必须带 features=itemOpusStyle 才有 opus 结构（见 _fetch_dynamics）
    check("OPUS 只有摘要时输出摘要",
          bm._dyn_text(opus("3b", "希望我bot还在")) == "希望我bot还在",
          repr(bm._dyn_text(opus("3b", "希望我bot还在"))))
    opus_item = dyn("3c", "", 1000, major="MAJOR_TYPE_OPUS", extra_major={
        "opus": {"title": "别爆", "summary": {"text": "希望我bot还在"},
                 "pics": [{"url": "http://i0/p.jpg"}]}})
    check("OPUS 标题与摘要合并", bm._dyn_text(opus_item) == "别爆\n希望我bot还在",
          repr(bm._dyn_text(opus_item)))

    opus_rich = dyn("3d", "", 1000, major="MAJOR_TYPE_OPUS", extra_major={
        "opus": {"summary": {"rich_text_nodes": [
            {"text": "第一段"}, {"text": "第二段"}]}}})
    check("OPUS 富文本节点拼接", bm._dyn_text(opus_rich) == "第一段第二段",
          repr(bm._dyn_text(opus_rich)))
    check("无内容返回空串", bm._dyn_text(dyn("4")) == "")
    check("major.type 优先于 type_field",
          bm._dyn_major_type(archive("5", "BV1x", "t")) == "MAJOR_TYPE_ARCHIVE")
    check("OPUS 图片取 pics[].url",
          bm._dyn_images(opus("6", "x", pics=2)) == ["http://i0/pic0.jpg", "http://i0/pic1.jpg"])
    check("ARCHIVE 图片取 cover",
          bm._dyn_images(archive("7", "BV1x", "t")) == ["http://i2/cover.jpg"])
    check("ARCHIVE 的 bvid 提取", bm._dyn_bvid(archive("8", "BV1abc", "t")) == "BV1abc")
    check("普通动态没有 bvid", bm._dyn_bvid(opus("9", "x")) == "")
    check("ARCHIVE 链接指向视频",
          bm._dyn_link(archive("10", "BV1abc", "t")) == "https://www.bilibili.com/video/BV1abc")
    check("普通动态链接指向动态",
          bm._dyn_link(dyn("11", "x")) == "https://t.bilibili.com/11")
    check("pub_ts 转 int", bm._dyn_ts(dyn("12", "x", ts=1793)) == 1793)


# ----------------------------------------------------------------- 2 消息构造
def test_compose() -> None:
    print("\n[2] 消息构造")
    text = bm._compose([dyn("1", "单条动态")], [])
    check("单条动态含正文", "单条动态" in text)
    check("单条动态标注条数", "【动态更新 ×1】" in text)

    text = bm._compose([dyn(str(i), f"d{i}") for i in range(5)], [])
    check("超出上限只展示 3 条", text.count("【") == 1 and "另有 2 条" in text, text[:80])

    text = bm._compose([], [video("BV1", "投稿A"), video("BV2", "投稿B")])
    check("投稿段标题", "【投稿更新 ×2】" in text)
    check("投稿含 bvid 链接", "https://www.bilibili.com/video/BV1" in text)

    text = bm._compose([dyn("1", "x")], [video("BV1", "y")])
    check("动态+投稿同时出现", "【动态更新" in text and "【投稿更新" in text)
    check("空输入返回 None", bm._compose([], []) is None)

    long_text = bm._compose([dyn(str(i), "很长的正文" * 100) for i in range(3)], [])
    check("总长度受限（≤1501）", len(long_text) <= 1501, str(len(long_text)))


# ----------------------------------------------------------------- 3~12 行为
async def test_behaviour() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        s, bot = make_env(tmp)
        cfg = bm._cfg()

        print("\n[3] 基线：全新 uid 只记基线不推")
        subs({111: ["2"]})
        bm._save_state({})
        s["dyn"] = [dyn("100", "旧动态"), dyn("90", "更旧")]
        s["vid"] = [video("BVold", "旧稿")]
        r = await bm._tick(bot, cfg)
        check("首轮推 0 条", r[2] == 0 and s["sent"] == [], str(r))
        st = bm._load_state()["2"]
        check("记录了 2 条动态基线", len(st["dynamic"]) == 2, str(st))
        check("记录了 1 条投稿基线", len(st["video"]) == 1)
        check("就绪标记已写", st.get("dyn_ready") is True and st.get("vid_ready") is True)
        check("水位线=最新时间戳", st.get("dyn_wm") == 1000, str(st.get("dyn_wm")))

        print("\n[4] 新内容推送")
        s["sent"].clear()
        s["dyn"] = [dyn("110", "新动态", ts=1100)] + s["dyn"]
        r = await bm._tick(bot, cfg)
        check("推送 1 个会话", r[2] == 1 and len(s["sent"]) == 1, str(r))
        check("消息含新动态正文", "新动态" in s["sent"][0][2])
        check("状态已推进", "110" in bm._load_state()["2"]["dynamic"])

        print("\n[5] 水位线：窗口滑动不推旧内容")
        s["sent"].clear()
        s["dyn"] = s["dyn"] + [dyn("50", "古代动态", ts=500), dyn("60", "古代2", ts=600)]
        r = await bm._tick(bot, cfg)
        check("更老的内容不推送", r[2] == 0, str(r))

        print("\n[6] 推送失败：状态不推进")
        s["sent"].clear()
        s["push_exc"] = True
        s["dyn"] = [dyn("120", "会失败的新动态", ts=1200)] + s["dyn"]
        r = await bm._tick(bot, cfg)
        check("本轮计为失败", r[1] >= 1, str(r))
        check("状态未推进", "120" not in bm._load_state()["2"]["dynamic"])
        s["push_exc"] = False
        r = await bm._tick(bot, cfg)
        check("恢复后补推成功", r[2] == 1 and "120" in bm._load_state()["2"]["dynamic"])

        print("\n[7] 去重：动态里的 bvid 不会被投稿列表重复推")
        s["sent"].clear()
        s["dyn"] = [archive("200", "BVnew", "新视频", ts=2000)] + s["dyn"]
        s["vid"] = [video("BVnew", "新视频", created=2000)] + s["vid"]
        r = await bm._tick(bot, cfg)
        check("本轮推 1 条（作为投稿）", r[2] == 1 and len(s["sent"]) == 1, str(r))
        check("归类为投稿更新", "【投稿更新" in s["sent"][0][2], s["sent"][0][2][:40])
        s["sent"].clear()
        r = await bm._tick(bot, cfg)
        check("投稿列表出现同一 bvid 不再推", r[2] == 0, str(r))

        print("\n[8] 持久化：重启后不重复推")
        s["sent"].clear()
        before = bm._load_state()
        bm._save_state(json.loads(json.dumps(before)))  # 模拟重启：从文件重读
        r = await bm._tick(bot, cfg)
        check("重新加载状态后仍无推送", r[2] == 0, str(r))

        print("\n[9] 多会话：只推给订阅者")
        subs({111: ["2"], 222: ["999"], 333: ["2"]})
        s["sent"].clear()
        s["dyn"] = [dyn("300", "多会话测试", ts=3000)] + s["dyn"]
        r = await bm._tick(bot, cfg)
        targets = sorted({c for _, c, _ in s["sent"]})
        check("只推 111 和 333", targets == ["111", "333"], str(targets))

        print("\n[10] 接口失败：不写入就绪标记")
        bm._save_state({})
        s["dyn_exc"] = RuntimeError("boom")
        s["dyn"] = []
        r = await bm._tick(bot, cfg)
        check("计为失败", r[1] >= 1, str(r))

        print("\n[11] 状态文件损坏")
        bm.STATE_PATH.write_text("{坏 json", encoding="utf-8")
        check("load_state 容错返回 {}", bm._load_state() == {})

        print("\n[12] 空订阅")
        bm._save_subs({"group": {}, "private": {}})
        r = await bm._tick(bot, cfg)
        check("没有订阅时返回 (0,0,0)", r == (0, 0, 0), str(r))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def test_edge_baselines() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        s, bot = make_env(tmp)
        cfg = bm._cfg()

        print("\n[13] 旧格式状态：只有 video 单值")
        subs({111: ["2"]})
        bm._save_state({"2": {"video": "BVold"}})
        s["dyn"] = [dyn("100", "历史动态", ts=1000)]
        s["vid"] = [video("BVold", "旧稿", created=1000)]
        s["sent"].clear()
        r = await bm._tick(bot, cfg)
        check("动态历史不会被推", r[2] == 0, str(r))
        check("补建了动态基线", len(bm._load_state()["2"]["dynamic"]) == 1)

        print("\n[14] 本来没有动态的 UP")
        bm._save_state({})
        s["dyn"] = []
        s["vid"] = [video("BV1", "旧稿", created=1000)]
        s["sent"].clear()
        r = await bm._tick(bot, cfg)
        check("首轮只建基线", r[2] == 0, str(r))
        check("dyn_ready 已置位", bm._load_state()["2"].get("dyn_ready") is True)
        r = await bm._tick(bot, cfg)
        check("第二轮不再重建基线（不重复打印）", r[2] == 0, str(r))
        s["dyn"] = [dyn("900", "它发的第一条动态", ts=5000)]
        r = await bm._tick(bot, cfg)
        check("第一条动态能推送（不被吞）", r[2] == 1, str(r))

        print("\n[15] 迁移校准：老状态无水位线")
        bm._save_state({"2": {"dynamic": ["100"], "video": [],
                              "dyn_ready": True, "vid_ready": True}})
        s["dyn"] = [dyn("100", "已知", ts=1000), dyn("80", "更老", ts=800)]
        s["sent"].clear()
        r = await bm._tick(bot, cfg)
        check("首轮只校准不推", r[2] == 0, str(r))
        check("写入了水位线", bm._load_state()["2"].get("dyn_wm") == 1000,
              str(bm._load_state()["2"]))
        s["dyn"] = [dyn("110", "校准后的新动态", ts=1100)] + s["dyn"]
        r = await bm._tick(bot, cfg)
        check("校准后新内容正常推", r[2] == 1, str(r))

        print("\n[16] 投稿轮询门控")
        bm._save_state({})
        subs({111: ["2"]})
        s["dyn"] = []
        s["vid"] = [video("BV1", "稿", created=1000)]
        s["calls"].clear()
        bm._ROUND = 0
        cfg2 = dict(cfg)
        cfg2["video_every"] = 2
        await bm._tick(bot, cfg2)   # round 1
        await bm._tick(bot, cfg2)   # round 2
        await bm._tick(bot, cfg2)   # round 3
        video_calls = [c for c in s["calls"] if c[0] == "video"]
        check("video_every=2 时投稿轮询约半数", 1 <= len(video_calls) <= 2, str(len(video_calls)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------- 配置/校验
def test_config() -> None:
    print("\n[17] 配置钳制")
    check("默认 interval=45", bm._interval({}) == 45)
    check("interval 过小被抬到 30", bm._interval({"interval": 3}) == 30)
    check("interval 过大压到 3600", bm._interval({"interval": 99999}) == 3600)
    check("interval 非法回退默认", bm._interval({"interval": "abc"}) == 45)
    check("interval 字符串数字可用", bm._interval({"interval": "60"}) == 60)
    check("video_every 最小值 1", bm._video_every({"video_every": 0}) == 1)
    check("video_every 默认 1", bm._video_every({}) == 1)

    print("\n[18] uid 校验")
    check("普通 uid", bm._valid_uid("2") is True)
    check("16 位 MID 合法", bm._valid_uid("1234567890123456") is True)
    check("20 位合法", bm._valid_uid("1" * 20) is True)
    check("21 位非法", bm._valid_uid("1" * 21) is False)
    check("前导零非法", bm._valid_uid("007") is False)
    check("0 非法", bm._valid_uid("0") is False)
    check("全角数字非法", bm._valid_uid("１２３") is False)
    check("上标非法", bm._valid_uid("²") is False)
    check("空串非法", bm._valid_uid("") is False)
    check("字母非法", bm._valid_uid("abc") is False)

    print("\n[19] 错误分类")
    class HttpStatusError(Exception):
        pass

    class ApiError(Exception):
        pass

    check("412", "412" in bm._explain(HttpStatusError("HTTP status 412")))
    check("-352", "-352" in bm._explain(ApiError("Bilibili API error -352")))
    check("-101", "-101" in bm._explain(ApiError("Bilibili API error -101")))
    check("超时", "超时" in bm._explain(TimeoutError("timed out")))
    check("未知异常带类型名", "ValueError" in bm._explain(ValueError("x")))


async def test_push_and_say() -> None:
    """主动推送接口 + /say 定时。"""
    from aullbot import push, context
    from aullbot.tools import basics

    print("\n[21] 主动推送接口")
    sent: list[tuple] = []

    class QQ:
        async def post_group_msg(self, group_id=None, text=None):
            sent.append(("group", group_id, text))

        async def post_private_msg(self, user_id=None, text=None):
            sent.append(("private", user_id, text))

        async def post_group_forward_msg(self, gid=None, forward=None):
            sent.append(("fwd", gid, len(forward.content)))

        async def post_private_forward_msg(self, uid=None, forward=None):
            sent.append(("fwd", uid, len(forward.content)))

    class Bot:
        api = SimpleNamespace(qq=QQ())

    push.bind(Bot())
    check("绑定后可查询", push.is_bound() is True)
    check("群发成功", await push.send_group(1, "x") is True)
    check("私聊成功", await push.send_private(2, "x") is True)
    check("按类型发送", await push.send(0, 3, "x") is True)

    sent.clear()
    n = await push.send_many([("group", 1), ("group", 1), ("private", 2)], "广播", gap=0)
    check("批量去重后成功 2 条", n == 2, str(n))
    check("批量目标正确", [k for k, *_ in sent] == ["group", "private"], str(sent))

    sent.clear()
    ok = await push.send_forward(0, 9, [("A", "1"), ("B", "2")], nickname="测试")
    check("合并转发成功", ok is True)
    check("节点数正确", sent and sent[0][2] == 2, str(sent))

    check("非法群号返回 False", await push.send_group("abc", "x") is False)
    check("空 blocks 返回 False", await push.send_forward(0, 1, []) is False)

    print("\n[22] /say 定时（text-first 两参数）")
    context.set_context(Bot(), 0, "100000001", cache_path=".", user_role="owner", sender_id="1")

    check("无延迟原样返回", await basics.say("你好") == "你好")
    check("普通文本原样返回", await basics.say("hello world") == "hello world")
    check("延迟 0 立刻返回", await basics.say("立刻", 0) == "立刻")
    check("负数延迟被拒", "负数" in await basics.say("x", -5))
    check("超长延迟被拒", "不能超过" in await basics.say("x", 999999))
    check("空内容提示用法", "用法" in await basics.say(""))
    check("delay 非数字时拼回正文",
          await basics.say("hello", "world") == "hello world")
    check("字符串数字延迟可用",
          "已排队" in await basics.say("内容", "5"))

    sent.clear()
    reply = await basics.say("一秒后发", 1)
    check("延迟任务已排队", "已排队" in reply, reply)
    check("排队时还没发送", sent == [], str(sent))
    await asyncio.sleep(1.4)
    check("到点后确实发送了", len(sent) == 1 and sent[0][2] == "一秒后发", str(sent))


def test_load_config() -> None:
    print("\n[20] #11 配置兜底")
    from aullbot.history_utils import HistoryManager

    tmp = Path(tempfile.mkdtemp())
    try:
        base = tmp / "bot_data"
        (base / "group" / "111").mkdir(parents=True)
        (base / "group" / "222").mkdir(parents=True)
        (base / "group" / "222" / "config.json").write_text("[]", encoding="utf-8")
        (base / "group" / "333").mkdir(parents=True)
        (base / "group" / "333" / "config.json").write_text(
            '{"prompt": [{"role": "system", "content": "x"}]}', encoding="utf-8")

        mgr = HistoryManager(str(base))
        check("文件缺失 → {}", mgr.load_config(111, 0) == {})
        check("内容是 [] → {}", mgr.load_config(222, 0) == {})
        check("正常配置原样返回",
              mgr.load_config(333, 0)["prompt"][0]["content"] == "x")
        check("read_json 缺失仍是 []（不影响其它调用方）",
              mgr.read_json(str(base / "nope.json")) == [])
        check("read_history 缺失仍是 []", mgr.read_history(999, 0) == [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("=" * 60)
    print("bilibili_monitor 完整回归测试")
    print("=" * 60)
    test_parse()
    test_compose()
    asyncio.run(test_behaviour())
    asyncio.run(test_edge_baselines())
    asyncio.run(test_push_and_say())
    test_config()
    test_load_config()

    print("\n" + "=" * 60)
    if FAIL:
        print(f"结果：{PASS} 通过 / {len(FAIL)} 失败")
        for item in FAIL:
            print(f"  ✗ {item}")
        return 1
    print(f"结果：{PASS} 通过 / 0 失败 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

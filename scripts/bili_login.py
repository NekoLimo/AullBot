#!/usr/bin/env python3
"""B站扫码登录，自动写入 .env。

用法（在项目根目录执行）：
    ./.venv/bin/python scripts/bili_login.py            # 扫码登录并写入 .env
    ./.venv/bin/python scripts/bili_login.py --check    # 只校验 .env 里现有凭据
    ./.venv/bin/python scripts/bili_login.py --dry-run  # 只生成二维码，不轮询
    ./.venv/bin/python scripts/bili_login.py --no-save  # 登录但不写文件

做什么：
    1. 生成登录二维码（终端直接显示 + 存 qr.png）
    2. 轮询扫码状态，成功后从返回的 URL / Set-Cookie 里取
       SESSDATA / bili_jct / DedeUserID / buvid3 / buvid4 / ac_time_value
    3. 用 nav 接口验证登录态，打印昵称和 UID
    4. 把凭据写进项目根目录的 .env（保留其它变量，备份原文件，权限 600）

只依赖 httpx + qrcode（项目虚拟环境里都有）。
"""
from __future__ import annotations

import asyncio
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import qrcode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ENV_FILE, confirm, mask, read_env, write_values  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
QR_PNG = ROOT / "qr.png"

QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"user-agent": BROWSER_UA, "referer": "https://www.bilibili.com/"}

CODE_TEXT = {
    0: "✅ 登录成功",
    86038: "⌛ 二维码已失效",
    86090: "📱 已扫码，请在手机上确认",
    86101: "⏳ 等待扫码",
}

# 写进 .env 的变量名 -> cookie 里的键
ENV_KEYS = {
    "BILI_SESSDATA": "SESSDATA",
    "BILI_JCT": "bili_jct",
    "BILI_DEDEUSERID": "DedeUserID",
    "BILI_BUVID3": "buvid3",
    "BILI_BUVID4": "buvid4",
    "BILI_AC_TIME_VALUE": "ac_time_value",
}
REQUIRED = ("SESSDATA", "bili_jct")


# ---------------------------------------------------------------- 二维码
def qr_ascii(url: str) -> str:
    """半高块渲染，终端里直接能扫。"""
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    lines = []
    for y in range(0, len(matrix), 2):
        row = []
        for x in range(len(matrix[0])):
            top = matrix[y][x]
            bottom = matrix[y + 1][x] if y + 1 < len(matrix) else False
            row.append("█" if top and bottom else "▀" if top else "▄" if bottom else " ")
        lines.append("".join(row))
    return "\n".join(lines)


def save_qr(url: str) -> Path:
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color="#fb7299", back_color="white").save(QR_PNG)
    return QR_PNG


# ---------------------------------------------------------------- 凭据解析
def cred_from_url(url: str) -> dict[str, str]:
    query = parse_qs(urlparse(url).query)
    return {key: (query.get(key) or [""])[0] for key in ENV_KEYS.values()}


def cred_from_set_cookie(headers: list[str]) -> dict[str, str]:
    jar: dict[str, str] = {}
    for header in headers:
        parsed = SimpleCookie()
        try:
            parsed.load(header)
        except Exception:
            continue
        jar.update({k: m.value for k, m in parsed.items()})
    return {key: jar.get(key, "") for key in ENV_KEYS.values()}


def cookie_header(cred: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cred.items() if v)


def merge_cred(primary: dict[str, str], fallback: dict[str, str]) -> dict[str, str]:
    return {k: primary.get(k) or fallback.get(k, "") for k in ENV_KEYS.values()}


# ---------------------------------------------------------------- 网络
async def generate_qr(hc: httpx.AsyncClient) -> tuple[str, str]:
    resp = await hc.get(QR_GENERATE, headers=HEADERS)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"生成二维码失败: {payload.get('code')} {payload.get('message')}")
    data = payload.get("data") or {}
    url, key = data.get("url", ""), data.get("qrcode_key", "")
    if not url or not key:
        raise RuntimeError(f"响应缺少 url/qrcode_key: {payload}")
    return url, key


async def poll_once(hc: httpx.AsyncClient, key: str) -> tuple[dict, list[str]]:
    resp = await hc.get(QR_POLL, params={"qrcode_key": key}, headers=HEADERS)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"轮询失败: code={payload.get('code')} {payload.get('message')}")
    return payload.get("data") or {}, resp.headers.get_list("set-cookie")


async def verify(cookie: str) -> tuple[bool, dict]:
    async with httpx.AsyncClient(timeout=20, trust_env=False) as hc:
        resp = await hc.get(NAV_URL, headers={**HEADERS, "cookie": cookie})
        payload = resp.json()
    data = payload.get("data") or {}
    return bool(data.get("isLogin")), {
        "code": payload.get("code"),
        "uname": data.get("uname"),
        "mid": data.get("mid"),
    }


# ---------------------------------------------------------------- .env 写入
# ---------------------------------------------------------------- 命令
async def login_qr(assume_yes: bool = False) -> dict[str, str] | None:
    """扫码登录，成功返回凭据 dict；失败返回 None。

    只负责"拿到并验证凭据"，不写 .env —— 写文件交给调用方
    （CLI 的 do_login、或 init_env.py 汇总后一起写）。
    """
    async with httpx.AsyncClient(timeout=20, trust_env=False,
                                 follow_redirects=True) as hc:
        for attempt in range(1, 4):
            try:
                url, key = await generate_qr(hc)
            except Exception as e:
                print(f"❌ {type(e).__name__}: {e}")
                return None

            print(f"\n=== 第 {attempt} 张二维码（约 3 分钟有效）===")
            print(f"二维码图片: {save_qr(url)}")
            print("用 B站 App「扫一扫」扫下面这块（或直接打开链接）:\n")
            print(qr_ascii(url))
            print(f"\n链接: {url}\n等待扫码…\n")

            last = None
            for _ in range(150):          # 150 × 2s = 5 分钟
                try:
                    data, set_cookie = await poll_once(hc, key)
                except Exception as e:
                    print(f"  轮询异常: {type(e).__name__}: {e}")
                    await asyncio.sleep(2)
                    continue

                code = int(data.get("code", -1))
                if code != last:
                    print(f"  → {CODE_TEXT.get(code, f'未知状态 {code}')}")
                    last = code

                if code == 86038:
                    print("  二维码失效，重新生成…\n")
                    break
                if code != 0:
                    await asyncio.sleep(2)
                    continue

                cred = merge_cred(cred_from_url(data.get("url", "")),
                                  cred_from_set_cookie(set_cookie))
                missing = [k for k in REQUIRED if not cred.get(k)]
                if missing:
                    print(f"❌ 扫码成功但凭据不全，缺: {missing}")
                    print(f"   set-cookie: {set_cookie}")
                    return None

                ok, info = await verify(cookie_header(cred))
                print("\n[凭据] " + " | ".join(
                    f"{k} {mask(v)}" for k, v in cred.items() if v))
                print(f"[校验] isLogin={ok} uname={info.get('uname')} "
                      f"mid={info.get('mid')}")
                if not ok:
                    print("⚠️  nav 未通过（可能被限流），凭据仍返回")
                if not cred["DedeUserID"] and info.get("mid"):
                    cred["DedeUserID"] = str(info["mid"])
                return cred
            else:
                print("  轮询超时，重新生成…\n")
    print("❌ 连续 3 张二维码都失效，请重试")
    return None


async def do_login(save: bool, assume_yes: bool = False) -> int:
    cred = await login_qr(assume_yes)
    if cred is None:
        return 1

    print("\n写入 .env 的字段：")
    for env_name, cookie_key in ENV_KEYS.items():
        value = cred.get(cookie_key, "")
        if value:
            print(f"  {env_name:<20} {mask(value)}")

    if not save:
        print("\n[--no-save] 未写入 .env")
        return 0

    if not confirm("\n写入 .env？", default=True, assume_yes=assume_yes):
        print("已跳过写入。")
        return 0

    old_ac = read_env().get("BILI_AC_TIME_VALUE", "")
    if not cred.get("ac_time_value") and old_ac:
        cred["ac_time_value"] = old_ac
    write_values({name: cred.get(key, "") for name, key in ENV_KEYS.items()})
    print(f"✅ 已写入 {ENV_FILE}（原文件备份为 .env.bak，权限 600）")
    print("   重启 bot 生效")
    return 0


async def do_check() -> int:
    env = read_env()
    cred = {key: env.get(name, "") for name, key in ENV_KEYS.items()}
    missing = [name for name, key in ENV_KEYS.items() if key in REQUIRED and not cred[key]]
    if missing:
        print(f"❌ .env 缺少: {missing}")
        return 1
    print(f"读取 {ENV_FILE}")
    ok, info = await verify(cookie_header(cred))
    print(f"isLogin={ok} uname={info.get('uname')} mid={info.get('mid')} code={info.get('code')}")
    if not ok:
        print("⚠️  未登录：可能已过期，或被风控降级成匿名（-101）。稍后重试或重新扫码。")
    return 0 if ok else 2


def main() -> int:
    args = sys.argv[1:]
    started = time.strftime("%H:%M:%S")

    if "--check" in args:
        return asyncio.run(do_check())

    save = "--no-save" not in args
    if "--dry-run" in args:
        async def dry() -> int:
            async with httpx.AsyncClient(timeout=20, trust_env=False) as hc:
                url, _ = await generate_qr(hc)
            print(f"[dry-run {started}] 二维码已生成: {save_qr(url)}")
            print(url)
            return 0

        return asyncio.run(dry())

    assume_yes = "--yes" in args or "-y" in args
    current = read_env()
    have = [name for name in ENV_KEYS if current.get(name)]
    if have:
        print(f".env 里已有 {len(have)} 项 B站凭据：")
        for name in have:
            print(f"  {name:<20} {mask(current[name])}")
        if not confirm("要重新扫码覆盖吗？", default=True, assume_yes=assume_yes):
            print("已取消。")
            return 0
    else:
        print(".env 里还没有 B站凭据，开始扫码登录。")

    return asyncio.run(do_login(save, assume_yes))


if __name__ == "__main__":
    raise SystemExit(main())

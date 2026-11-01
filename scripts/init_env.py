#!/usr/bin/env python3
"""交互式初始化 .env —— 所有环境变量的统一入口。

    python scripts/init_env.py          # 交互式
    python scripts/init_env.py --yes    # 全部取默认，不提问

覆盖：
  LLM_API_KEY        LLM 密钥
  QQ_NUMBER          bot 自己的 QQ 号
  BILI_*             B站凭据（可选，直接调扫码登录）

已存在的值会打码显示，回车保留原值。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ask, confirm, mask, read_env, write_values  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

LLM_KEYS = (
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_EFFORT",
    "LLM_THINKING",
    "LLM_MAX_TOOL_ITERATIONS",
)

BILI_KEYS = (
    "BILI_SESSDATA",
    "BILI_JCT",
    "BILI_DEDEUSERID",
    "BILI_BUVID3",
    "BILI_BUVID4",
    "BILI_AC_TIME_VALUE",
)


def show_current() -> dict[str, str]:
    current = read_env()
    print(f"\n当前 {ENV_FILE}：")
    if not current:
        print("  （不存在或为空）")
    for key in ("LLM_API_KEY", "QQ_NUMBER", *LLM_KEYS, *BILI_KEYS):
        if key == "LLM_API_KEY" or key in BILI_KEYS:
            shown = mask(current.get(key, ""))
        else:
            shown = current.get(key, "（未设置）")
        print(f"  {key:<20} {shown}")
    return current


def collect_basic(current: dict[str, str], assume_yes: bool) -> dict[str, str]:
    print("\n--- 基础配置 ---")
    key = ask(
        f"LLM_API_KEY（当前 {mask(current.get('LLM_API_KEY', ''))}，回车保留）",
        "", secret=True, assume_yes=assume_yes,
    )
    qq = ask(
        f"QQ_NUMBER（当前 {current.get('QQ_NUMBER', '未设置')}，回车保留）",
        "", assume_yes=assume_yes,
    )
    values = {"LLM_API_KEY": key, "QQ_NUMBER": qq}
    if not assume_yes and confirm("要调整模型配置吗？（默认 deepseek-v4-pro 即可）",
                                  default=False):
        model = ask(f"LLM_MODEL（当前 {current.get('LLM_MODEL', '默认')}）",
                    "", assume_yes=assume_yes)
        effort = ask(f"LLM_EFFORT  low|high|max（当前 {current.get('LLM_EFFORT', 'high')}）",
                     "", assume_yes=assume_yes)
        thinking = ask(f"LLM_THINKING  enabled|disabled（当前 {current.get('LLM_THINKING', 'disabled')}）",
                       "", assume_yes=assume_yes)
        values.update({"LLM_MODEL": model, "LLM_EFFORT": effort, "LLM_THINKING": thinking})
    return values


def collect_bili(current: dict[str, str], assume_yes: bool) -> dict[str, str]:
    have = [k for k in BILI_KEYS if current.get(k)]
    print("\n--- B站凭据（可选，用于 bilibili_monitor）---")
    if have:
        print(f"  已有 {len(have)} 项：")
        for key in have:
            print(f"    {key:<20} {mask(current[key])}")

    default_scan = False if assume_yes else (not have)
    if not confirm("现在扫码登录 B站？", default=default_scan, assume_yes=assume_yes):
        print("  跳过（之后可单独运行: python scripts/bili_login.py）")
        return {}

    import bili_login

    cred = asyncio.run(bili_login.login_qr(assume_yes=assume_yes))
    if not cred:
        print("  ⚠️  扫码未完成，B站凭据保持原样")
        return {}

    old_ac = current.get("BILI_AC_TIME_VALUE", "")
    if not cred.get("ac_time_value") and old_ac:
        cred["ac_time_value"] = old_ac
    return {name: cred.get(key, "") for name, key in bili_login.ENV_KEYS.items()}


def main() -> int:
    assume_yes = "--yes" in sys.argv[1:] or "-y" in sys.argv[1:]

    print("=" * 52)
    print("AullBot 环境变量初始化")
    print("=" * 52)

    current = show_current()
    values = collect_basic(current, assume_yes)
    values.update(collect_bili(current, assume_yes))

    changes = {k: v for k, v in values.items() if v}
    if not changes:
        print("\n没有需要写入的内容。")
        return 0

    print("\n将写入：")
    for key, value in changes.items():
        shown = mask(value) if ("KEY" in key or key in BILI_KEYS) else value
        print(f"  {key:<20} {shown}")

    if not confirm("\n确认写入 .env？", default=True, assume_yes=assume_yes):
        print("已取消。")
        return 0

    write_values(changes)
    print(f"✅ 已写入 {ENV_FILE}（原文件备份为 .env.bak，权限 600）")
    print("\n下一步：")
    print("  python scripts/init_data.py      # 初始化 bot_data")
    print("  uv run python -u -m aullbot.main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

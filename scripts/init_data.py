#!/usr/bin/env python3
"""交互式初始化 bot_data（首次部署用）。

    python scripts/init_data.py          # 交互式
    python scripts/init_data.py --yes    # 全部取默认
    python scripts/init_data.py --force  # 已有数据也重建

系统提示词**不在终端里手打**（容易漏行、被判错），只接受两种来源：
  1. 指定一个已有的 .md / .txt 文件路径
  2. 生成空模板 scripts/assets/system_prompt.md，你填完再跑一次
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ask, choose, confirm  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS = BASE_DIR / "scripts" / "assets"
BOT_DATA = BASE_DIR / "bot_data"

PROMPT_MD = ASSETS / "system_prompt.md"
TEMPLATE = ASSETS / "template_config.json"

DEFAULT_PROMPT = "You are a helpful assistant."
TEMPLATE_HINT = """<!-- 在这里写你的系统提示词，保存后重新运行: python scripts/init_data.py -->

你是一个有帮助的助手。

"""


def existing_groups() -> list:
    path = BOT_DATA / "group" / "group_list.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def pick_mode(assume_yes: bool) -> str:
    groups = existing_groups()
    if not groups:
        print("✓ bot_data 为空，执行首次初始化\n")
        return "fresh"

    print(f"⚠️  bot_data 里已有 {len(groups)} 个群的数据\n")
    picked = choose("要怎么做？", [
        "保留现有数据，只补齐缺失文件（推荐）",
        "全部重建（清空群/私聊列表，各群目录不动）",
        "退出",
    ], default=1, assume_yes=assume_yes)
    return {1: "keep", 2: "rebuild", 3: "quit"}[picked]


def read_prompt_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        print(f"  ❌ 文件不存在: {path}")
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"  ❌ 读取失败: {type(e).__name__}: {e}")
        return None
    if not text:
        print(f"  ❌ 文件是空的: {path}")
        return None
    return text


def pick_prompt(assume_yes: bool) -> tuple[str, str] | None:
    """返回 (提示词, 来源) 或 None（需要用户先去填文件）。"""
    has_asset = PROMPT_MD.exists() and PROMPT_MD.read_text(encoding="utf-8").strip()

    options = []
    if has_asset:
        options.append(f"用 {PROMPT_MD.relative_to(BASE_DIR)}（{len(PROMPT_MD.read_text(encoding='utf-8').strip())} 字）")
    options.append("指定其它文件路径")
    options.append(f"生成空模板 {PROMPT_MD.name}，我填完再跑一次")
    options.append("用最小默认（You are a helpful assistant.）")

    picked = choose("系统提示词从哪来？", options, default=1, assume_yes=assume_yes)
    index = 1

    if has_asset:
        if picked == index:
            text = PROMPT_MD.read_text(encoding="utf-8").strip()
            return text, f"assets/system_prompt.md（{len(text)} 字）"
        index += 1

    if picked == index:                       # 指定路径
        raw = ask("  文件路径（支持 ~ 和相对路径）", "", assume_yes=assume_yes)
        if raw:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            text = read_prompt_file(path)
            if text:
                return text, f"{path}（{len(text)} 字）"
        print("  没拿到有效文件，改用最小默认")
        return DEFAULT_PROMPT, "最小默认"
    index += 1

    if picked == index:                       # 生成空模板
        ASSETS.mkdir(parents=True, exist_ok=True)
        PROMPT_MD.write_text(TEMPLATE_HINT, encoding="utf-8")
        print(f"\n  ✅ 已生成空模板: {PROMPT_MD}")
        print("     编辑它，把你的提示词写进去，然后重新运行:")
        print("       python scripts/init_data.py")
        return None
    return DEFAULT_PROMPT, "最小默认"


def main() -> int:
    assume_yes = "--yes" in sys.argv[1:] or "-y" in sys.argv[1:]
    force = "--force" in sys.argv[1:]

    print("=" * 52)
    print("AullBot 数据初始化")
    print("=" * 52)

    mode = "rebuild" if force else pick_mode(assume_yes)
    if mode == "quit":
        print("已取消，什么都没改。")
        return 0

    picked = pick_prompt(assume_yes)
    if picked is None:
        return 0                              # 已生成模板，等用户填完再来
    prompt, source = picked

    print("\n将要执行：")
    if mode == "keep":
        print("  · 保留现有 group/private 列表")
    else:
        print("  · 重置 group_list.json / private_list.json 为空")
    print(f"  · 写 system_prompt.json / .md  ← {source}")
    if TEMPLATE.exists():
        print("  · 复制 template_config.json")
    else:
        print(f"  ⚠️  缺少 {TEMPLATE}，跳过（新会话建不了配置）")

    if not confirm("\n确认执行？", default=True, assume_yes=assume_yes):
        print("已取消。")
        return 0

    (BOT_DATA / "group").mkdir(parents=True, exist_ok=True)
    (BOT_DATA / "private").mkdir(parents=True, exist_ok=True)

    if mode != "keep":
        for path, name in (
            (BOT_DATA / "group" / "group_list.json", "group_list"),
            (BOT_DATA / "private" / "private_list.json", "private_list"),
        ):
            path.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ✅ {name}.json")

    (BOT_DATA / "system_prompt.json").write_text(
        json.dumps({"role": "system", "content": prompt}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (BOT_DATA / "system_prompt.md").write_text(prompt, encoding="utf-8")
    print(f"  ✅ system_prompt.json / .md  ← {source}")

    if TEMPLATE.exists():
        shutil.copy(TEMPLATE, BOT_DATA / "template_config.json")
        print("  ✅ template_config.json")

    print("\n完成。下一步：")
    print("  1. python scripts/init_env.py    # 没配 .env 的话")
    print("  2. uv run python -u -m aullbot.main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

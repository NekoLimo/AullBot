# src/aullbot/tools/img.py
"""图片生成：把文本渲染成白底黑字图片。

不再使用合并字体。渲染时直接读取 fonts/ 下的两份 OFL 字体，
按字符在 JetBrains Mono（拉丁/符号）与 Source Han Sans CN（CJK）之间切换。
"""
import os
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .. import context
from aullbot.command_registry import command
from aullbot.rbac import require_role_async
from aullbot.module_meta import ModuleMeta

MODULE = ModuleMeta(
    name="img",
    author="Limo",
    description="图片生成（白底黑字，多字体自动切换）",
    default_enabled=True,
    tags=("media", "image"),
)

# src/aullbot/tools/img.py -> 仓库根目录/fonts
FONT_DIR = Path(__file__).parents[3] / "fonts"
FONT_FILES = {
    "mono": FONT_DIR / "JetBrainsMonoNerdFont-Regular-v1.2.ttf",
    "sans": FONT_DIR / "SourceHanSansCN-Regular.otf",
}

# auto：按字符切换；mono/sans：整图强制一种字体。
# 需要改默认行为时可设环境变量 AULLBOT_IMG_FONT=auto|mono|sans（重启生效）。
FONT_MODE = os.environ.get("AULLBOT_IMG_FONT", "auto").strip().lower()
if FONT_MODE not in {"auto", "mono", "sans"}:
    FONT_MODE = "auto"

FONT_SIZE = 80
PADDING = 50
MAX_WIDTH = 8000
MAX_HEIGHT = 8000
MAX_PIXELS = 12_000_000


def _load_fonts(size: int = FONT_SIZE) -> dict[str, ImageFont.FreeTypeFont | None]:
    """加载 fonts/ 下的字体；单个缺失时返回 None，由调用方回退到另一种。"""
    fonts: dict[str, ImageFont.FreeTypeFont | None] = {}
    for key, path in FONT_FILES.items():
        try:
            fonts[key] = ImageFont.truetype(str(path), size=size)
        except OSError:
            print(f"[img] 字体加载失败: {path}")
            fonts[key] = None
    return fonts


def _font_key(ch: str) -> str:
    """为单个字符选择字体。

    * PUA（Nerd Fonts 图标）→ mono；
    * CJK 部首/假名/谚文/全角符号/汉字 → sans；
    * 其余（ASCII、拉丁、常见符号）→ mono。
    """
    if FONT_MODE != "auto":
        return FONT_MODE
    code = ord(ch)
    if 0xE000 <= code <= 0xF8FF or 0xF0000 <= code <= 0x10FFFD:
        return "mono"
    if code >= 0x2E80:
        return "sans"
    return "mono"


def _runs(line: str, fonts: dict) -> list[tuple[str, str]]:
    """把一行拆成连续同字体的片段，保留片段内的字距/连字效果。"""
    runs: list[list[str]] = []
    for ch in line:
        key = _font_key(ch)
        if fonts.get(key) is None:
            key = "sans" if key == "mono" else "mono"
        if not runs or runs[-1][0] != key:
            runs.append([key, ch])
        else:
            runs[-1][1] += ch
    return [(key, chunk) for key, chunk in runs]


def render_text_image(
    text: str, size: int = FONT_SIZE, padding: int = PADDING
) -> Image.Image:
    """把文本渲染成白底黑字图片（纯函数，便于单独测试）。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    lines = text.split("\n")

    fonts = _load_fonts(size)
    if not any(fonts.values()):
        raise FileNotFoundError(
            "字体文件缺失，请确认: "
            + "、".join(str(path) for path in FONT_FILES.values())
        )

    def font_of(key: str) -> ImageFont.FreeTypeFont:
        font = fonts.get(key) or fonts.get("sans") or fonts.get("mono")
        assert font is not None
        return font

    # 统一基线：所有字体取最大的 ascent/descent，避免中英混排上下错位
    metrics = [font.getmetrics() for font in fonts.values() if font is not None]
    max_ascent = max(ascent for ascent, _ in metrics)
    max_descent = max(descent for _, descent in metrics)
    line_height = max_ascent + max_descent

    layout: list[tuple[list[tuple[str, str, float]], float]] = []
    max_line_width = 0.0
    for line in lines:
        runs = _runs(line, fonts)
        widths = [
            (key, chunk, font_of(key).getlength(chunk)) for key, chunk in runs
        ]
        line_width = sum(width for _, _, width in widths)
        layout.append((widths, line_width))
        max_line_width = max(max_line_width, line_width)

    image_width = int(round(max_line_width)) + padding * 2
    image_height = line_height * len(lines) + padding * 2
    if image_width > MAX_WIDTH or image_height > MAX_HEIGHT:
        raise ValueError(
            f"文本过长（{image_width}×{image_height}），请缩短后再试"
        )
    if image_width * image_height > MAX_PIXELS:
        raise ValueError(
            f"图片过大（{image_width}×{image_height}），请缩短后再试"
        )

    image = Image.new("RGB", (image_width, image_height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for index, (widths, line_width) in enumerate(layout):
        x = padding + (max_line_width - line_width) / 2
        baseline = padding + index * line_height + max_ascent
        for key, chunk, width in widths:
            draw.text(
                (x, baseline),
                chunk,
                font=font_of(key),
                fill=(0, 0, 0),
                anchor="ls",
            )
            x += width
    return image


@command("/img")
@require_role_async("user")
async def img(text: str, get_con: bool = True) -> str | None:
    """生成白底黑字图片并发送。

    字体：JetBrains Mono（拉丁/符号）+ Source Han Sans CN（CJK）自动切换。
    环境变量 AULLBOT_IMG_FONT=auto|mono|sans 可强制字体模式（重启生效）。
    """
    if get_con:
        raw = context.get_raw_message()
        match = re.search(r"^/img\s?(.*)", raw, re.DOTALL)
        if not match:
            return "未提供文本"
        # 从原文取完整内容，保留空格和换行
        text = match.group(1)

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    try:
        image = render_text_image(text)
    except (FileNotFoundError, ValueError) as e:
        return str(e)

    filename = f"img_{random.randint(100000, 999999)}.jpg"
    save_path = os.path.join(context.get_cache_path(), filename)
    image.save(save_path)

    bot = context.get_bot()
    chat_type = context.get_chat_type()
    chat_id = context.get_chat_id()

    try:
        if chat_type == 0:  # 群聊
            await bot.api.qq.send_group_image(chat_id, save_path)
        elif chat_type == 1:  # 私聊
            await bot.api.qq.send_private_image(chat_id, save_path)
        else:
            return "不支持的聊天类型"
    except Exception as e:
        return f"发送图片失败: {e}"
    return None

# others/img.py
"""手动测试图片渲染（不接入 bot）。

正式实现见 src/aullbot/tools/img.py；这里只做本地生成，方便肉眼检查字体效果。
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from aullbot.tools.img import render_text_image  # noqa: E402


def img(text: str) -> None:
    image = render_text_image(text)
    filename = f"img_{random.randint(100000, 999999)}.jpg"
    image.save(filename)
    print(f"图片已保存: {filename}")


if __name__ == "__main__":
    img("滚木 123 Hello 世界")

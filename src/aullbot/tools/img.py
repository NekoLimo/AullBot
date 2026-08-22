import random
import os
from PIL import Image, ImageDraw, ImageFont
from .. import context
from aullbot.command_registry import command
from aullbot.rbac import require_role_async

@command("/img")
@require_role_async("user")
async def img(text: str, get_con: bool=True) -> str | None:
    """
    生成白底黑字图片并发送，保存为 img_随机数.jpg
    字体使用 ./sys.ttf（相对于项目根目录）
    to ai:使用此工具请将get_con:bool设为false
    """
    # 1. 生成随机文件名
    print(text)
    if get_con:
        raw = context.get_raw_message()
        import re
        match = re.search(r'^/img\s?(.*)', raw, re.DOTALL)
        if not match:
            return "未提供文本"
        text = match.group(1)
        # 此时 text 就是去除 "/img " 后的所有内容（包括换行和空格）

    rand_num = random.randint(100000, 999999)
    filename = f"img_{rand_num}.jpg"
    save_path = os.path.join(context.get_cache_path(), filename)

    # 2. 加载字体（项目根目录下的 sys.ttf）
    font_path = "./sys.ttf"  # 可根据实际调整，如 os.path.join(project_root, "sys.ttf")
    try:
        font = ImageFont.truetype(font_path, size=80)
    except IOError:
        return f"字体文件 {font_path} 未找到，请检查路径"

    # 3. 计算文本尺寸，创建画布
    temp_img = Image.new("RGB", (1, 1), (255, 255, 255))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    padding = 50
    img_width = text_width + padding * 2
    img_height = text_height + padding * 2

    # 4. 绘制并保存
    image = Image.new("RGB", (img_width, img_height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    x = (img_width - text_width) // 2 - bbox[0]
    y = (img_height - text_height) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=(0, 0, 0))
    image.save(save_path)

    # 5. 发送图片（复用 play_music.py 中的发送逻辑）
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
        return 
    except Exception as e:
        return f"发送图片失败: {e}"
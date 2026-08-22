import random
from PIL import Image, ImageDraw, ImageFont

def img(text: str) -> None:
    """
    生成白底黑字图片，保存为 img_随机数.jpg，使用指定字体 ./sys.ttf
    """
    # 生成随机数（示例为 6 位，可根据需要调整）
    rand_num = random.randint(100000, 999999)
    filename = f"img_{rand_num}.jpg"

    # 加载字体（请确保 ./sys.ttf 存在）
    try:
        font = ImageFont.truetype("./sys.ttf", size=80)
    except IOError:
        raise FileNotFoundError("字体文件 ./sys.ttf 未找到，请检查路径")

    # 先估算文本尺寸，确定画布大小（留白边距 50 像素）
    # 使用临时临时图片测量文本尺寸
    temp_img = Image.new("RGB", (1, 1), (255, 255, 255))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    padding = 50
    img_width = text_width + padding * 2
    img_height = text_height + padding * 2

    # 创建最终画布（白色背景）
    image = Image.new("RGB", (img_width, img_height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    # 绘制黑色文本（居中）
    x = (img_width - text_width) // 2 - bbox[0]
    y = (img_height - text_height) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=(0, 0, 0))

    # 保存图片
    image.save(filename)
    print(f"图片已保存: {filename}")
    
if __name__ == "__main__":
    img("美丽莎死妈了")
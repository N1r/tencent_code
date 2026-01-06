import os
from PIL import Image, ImageDraw, ImageFont
import random

# ================= 配置 =================
INPUT_IMAGE = "output/test/test.jpg"
OUTPUT_IMAGE = "output/test/test_dd.png"  # 输出路径
TITLE_TEXT = "川普突然现身纽约，马斯克紧急发声！"  # ← 可修改

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

# 自动选择字体（Linux 兼容）
def get_font_path():
    possible_fonts = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",      # OpenCloudOS/CentOS
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",  # PIL 内置 fallback
    ]
    for font in possible_fonts:
        if os.path.exists(font):
            return font
    return "arial.ttf"  # 最终 fallback（PIL 内置）

FONT_PATH = get_font_path()
print(f"使用字体: {FONT_PATH}")

# ================= 工具函数 =================
def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    lines = []
    current_line = ""
    for char in text:
        if font.getlength(current_line + char) <= max_width:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    if current_line:
        lines.append(current_line)
    return lines


def draw_text_with_effects(draw, text, position, font, fill, outline_color="black", outline_width=3, shadow_color=None):
    x, y = position

    # 阴影（可选）
    if shadow_color:
        draw.text((x + 4, y + 4), text, font=font, fill=shadow_color)

    # 粗描边
    if outline_color and outline_width > 0:
        offsets = []
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx == 0 and dy == 0:
                    continue
                if dx*dx + dy*dy <= outline_width*outline_width:
                    offsets.append((dx, dy))
        for dx, dy in offsets:
            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)

    # 主文字
    draw.text((x, y), text, font=font, fill=fill)


def create_gradient_overlay(width, height, start_alpha=120, end_alpha=220, gradient_height_percent=0.45):
    gradient = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    grad_h = int(height * gradient_height_percent)
    start_y = height - grad_h
    for y in range(start_y, height):
        alpha = int(start_alpha + (end_alpha - start_alpha) * (y - start_y) / grad_h)
        draw.rectangle([(0, y), (width, y + 1)], fill=(0, 0, 0, alpha))
    return gradient

# ================= 封面生成函数 =================
def cover_making(image_path: str, output_path: str, translated_text: str = None):
    try:
        # 处理标题为空的情况
        if not translated_text or not isinstance(translated_text, str):
            print("⚠️ 标题为空，使用默认文本")
            translated_text = "封面标题占位符"

        # 打开并缩放背景图
        background = Image.open(image_path).convert('RGBA')
        orig_w, orig_h = background.size
        print(f"原始尺寸: {orig_w}x{orig_h}")

        # 等比缩放（以较短边为准）
        scale = min(TARGET_WIDTH / orig_w, TARGET_HEIGHT / orig_h)
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)
        background = background.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 创建画布并居中粘贴
        canvas = Image.new('RGBA', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 255))
        paste_x = (TARGET_WIDTH - new_w) // 2
        paste_y = (TARGET_HEIGHT - new_h) // 2
        canvas.paste(background, (paste_x, paste_y))

        # 叠加渐变遮罩
        gradient = create_gradient_overlay(TARGET_WIDTH, TARGET_HEIGHT)
        canvas = Image.alpha_composite(canvas, gradient)
        draw = ImageDraw.Draw(canvas)

        # 右上角“中英双语”
        font_bilingual = ImageFont.truetype(FONT_PATH, 50)
        text_bilingual = "中英双语"
        bbox = draw.textbbox((0, 0), text_bilingual, font=font_bilingual)
        pos = (TARGET_WIDTH - 50 - (bbox[2] - bbox[0]), 30)
        draw_text_with_effects(draw, text_bilingual, pos, font_bilingual,
                              fill="white", outline_color="black")

        # 自适应标题字体大小（最多3行）
        max_width = TARGET_WIDTH - 100
        font_size = 200
        lines = []
        final_font = None
        while font_size >= 65:
            try:
                font = ImageFont.truetype(FONT_PATH, font_size)
            except OSError:
                font = ImageFont.load_default()
            lines = wrap_text(translated_text, font, max_width)
            if len(lines) <= 3:
                final_font = font
                break
            font_size -= 5

        if final_font is None:
            final_font = ImageFont.truetype(FONT_PATH, 65)
            lines = wrap_text(translated_text, final_font, max_width)[:3]

        if len(lines) > 3:
            lines = lines[:3]
            # 截断第三行
            while len(lines[2]) > 0 and final_font.getlength(lines[2] + "...") > max_width:
                lines[2] = lines[2][:-1]
            lines[2] += "..."

        # 计算文字总高度
        sample_bbox = final_font.getbbox("测")
        line_height = (sample_bbox[3] - sample_bbox[1]) + 15
        total_h = len(lines) * line_height

        # === 关键修改：文字仅限制在渐变区域内 ===
        GRADIENT_HEIGHT_PERCENT = 0.45
        gradient_start_y = int(TARGET_HEIGHT * (1 - GRADIENT_HEIGHT_PERCENT))  # 55% 位置
        gradient_height = TARGET_HEIGHT - gradient_start_y
        bottom_margin = 40  # 底部留白
        usable_height = gradient_height - bottom_margin

        if total_h > usable_height:
            start_y = gradient_start_y + 10  # 顶对齐 + 小边距
        else:
            start_y = gradient_start_y + (usable_height - total_h) // 2

        # 随机颜色
        colors = ["#FF1493", "#FFD700", "#FF6347", "#00BFFF", "#32CD32", "#FF4500"]
        text_color = random.choice(colors)

        # 绘制每行
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=final_font)
            x = (TARGET_WIDTH - (bbox[2] - bbox[0])) // 2
            y = start_y + i * line_height
            draw_text_with_effects(draw, line, (x, y), final_font,
                                  fill=text_color, outline_color="black",
                                  shadow_color=(0, 0, 0, 180))

        # 保存（转为 RGB 避免透明问题）
        canvas.convert("RGB").save(output_path)
        print(f"✅ 封面已生成: {output_path}")

    except Exception as e:
        print(f"❌ 封面生成失败: {e}")
        import traceback
        traceback.print_exc()

# ================= 主程序 =================
if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_IMAGE), exist_ok=True)
    if not os.path.exists(INPUT_IMAGE):
        print(f"❌ 输入图片不存在: {INPUT_IMAGE}")
        print("请将一张 JPG 图片重命名为 'test.jpg' 放在 output/test/ 目录下")
    else:
        cover_making(INPUT_IMAGE, OUTPUT_IMAGE, TITLE_TEXT)
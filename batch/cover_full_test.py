import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ==================== 1. 基础配置 ====================
# 请确保路径下有对应的字体文件，如果没有，代码会回退到默认字体
FONT_PATH = "/root/VideoLingo/batch/Fonts/canger.ttf" 
if not os.path.exists(FONT_PATH):
    FONT_PATH = "arial.ttf" # Windows 用户可改为 "simhei.ttf"

HOT_KEYWORDS = ["美方", "委内瑞拉", "中方", "川普", "特朗普", "马斯克", "内幕"]
HIGHLIGHT_COLOR = "#FFD700"  # 金黄色
NORMAL_COLOR = "#FFFFFF"     # 纯白色
RED_ACCENT = "#E21918"       # 标志性的新闻红
BOX_COLOR = (0, 0, 0, 230)    # 80% 不透明度的黑框

# ==================== 2. 核心算法函数 ====================

def wrap_text(text, font, max_width):
    lines = []
    current_line = ""
    for char in text:
        if font.getlength(current_line + char) <= max_width:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    lines.append(current_line)
    return lines[:2] # 封面建议最多2行

def draw_styled_line(draw, line, font, x_start, y_top, box_h):
    """
    在黑框内实现文字垂直居中和多色渲染
    """
    # 获取文字的精确像素边框 (left, top, right, bottom)
    l, t, r, b = font.getbbox(line)
    actual_text_h = b - t
    
    # 【精准计算】: 让文字的视觉中心点与黑框的中心点重合
    # t 是字体的 ascent 偏移，必须减去它才能真正置顶开始计算
    vertical_offset = (box_h - actual_text_h) // 2 - t
    draw_y = y_top + vertical_offset

    curr_x = x_start
    temp_line = line
    
    # 逐字扫描高亮
    while temp_line:
        match_found = False
        for kw in HOT_KEYWORDS:
            if temp_line.startswith(kw):
                draw.text((curr_x, draw_y), kw, font=font, fill=HIGHLIGHT_COLOR)
                curr_x += font.getlength(kw)
                temp_line = temp_line[len(kw):]
                match_found = True
                break
        if not match_found:
            char = temp_line[0]
            draw.text((curr_x, draw_y), char, font=font, fill=NORMAL_COLOR)
            curr_x += font.getlength(char)
            temp_line = temp_line[1:]

# ==================== 3. 主绘图函数 ====================

def make_pro_cover(input_img, output_img, text):
    # 1. 基础画布
    bg = Image.open(input_img).convert('RGBA')
    bg = bg.resize((1920, 1080), Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=1)) # 稍微虚化背景增强文字对比
    canvas = Image.alpha_composite(bg, Image.new('RGBA', (1920, 1080), (0,0,0,30)))
    draw = ImageDraw.Draw(canvas)

    # 2. 绘制顶部标签 (防止 Overlap 的固定区)
    tag_f = ImageFont.truetype(FONT_PATH, 45)
    tag_t = " GLOBAL NEWS • 每日速递 "
    tw = tag_f.getlength(tag_t)
    draw.rectangle([0, 50, tw + 100, 120], fill=RED_ACCENT)
    draw.text((50, 62), tag_t, font=tag_f, fill="white")

    # 3. 绘制主标题
    title_f = ImageFont.truetype(FONT_PATH, 145)
    lines = wrap_text(text, title_f, 1600)
    
    box_h = 180  # 每个黑框的高度
    line_spacing = 25
    total_h = len(lines) * box_h + (len(lines)-1) * line_spacing
    
    # 动态计算起始位置：从底部向上推，但最高不能超过 200px
    current_y = max(1080 - total_h - 120, 200)

    for line in lines:
        lw = title_f.getlength(line)
        # 绘制背景黑框
        box_left = 60
        box_right = box_left + lw + 100
        draw.rectangle([box_left, current_y, box_right, current_y + box_h], fill=BOX_COLOR)
        # 绘制左侧红杠
        draw.rectangle([box_left, current_y, box_left + 15, current_y + box_h], fill=RED_ACCENT)
        
        # 调用精准对齐绘制
        draw_styled_line(draw, line, title_f, box_left + 45, current_y, box_h)
        
        current_y += box_h + line_spacing

    canvas.convert('RGB').save(output_img)
    print(f"Done! {output_img}")

# 测试运行
if __name__ == "__main__":
    # 请确保你有一张名为 test.jpg 的图片用于测试
    test_title = "委内瑞拉新主事前, 美方数月前已布局"
    if os.path.exists("test.jpg"):
        make_pro_cover("test.jpg", "demo_output.jpg", test_title)
    else:
        print("请在目录下放一张 test.jpg 图片进行测试")
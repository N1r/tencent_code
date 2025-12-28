import os
import random
import yaml
import requests
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

# ==================== 常量配置（按需修改） ====================
OUTPUT_DIR = 'output'
COVER_SUFFIX = '.jpg'
NEW_COVER_SUFFIX = '_new.png'
# Linux 字体路径：优先使用 NotoSansCJK，无则自动回退系统字体
FONT_PATH = "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Black.ttc"
TAG = '英语新闻, 英语学习, 川普, 马斯克, 咨询直通车, 社会观察局, 热点深度观察'
YAML_OUTPUT_FILE = 'config_bili.yaml'

# API 配置
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai'
API_MODEL = 'gemini-2.5-flash-lite'

# 文字颜色列表
COLOR_LIST = ["#FF1493", "#FF69B4", "#FFD700", "#FF6347", "#00BFFF", "#32CD32", "#FF4500", "#9370DB", "#FF8C00", "#1E90FF"]

# ==================== 核心工具函数 ====================
def find_files_with_suffix(directory, suffix):
    """查找指定目录下所有带指定后缀的文件"""
    return [os.path.join(root, file) 
            for root, _, files in os.walk(directory) 
            for file in files if file.endswith(suffix)]

def wrap_text(text, font, max_width):
    """文本自动换行（适配中文字符）"""
    lines, current_line = [], ""
    for char in text:
        if font.getlength(current_line + char) <= max_width:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    if current_line:
        lines.append(current_line)
    return lines

def draw_text_with_effects(draw, text, position, font, fill, outline_color="black", shadow_color="rgba(0,0,0,180)", shadow_offset=(3,3)):
    """绘制带描边、阴影的文字"""
    x, y = position
    dx, dy = shadow_offset
    # 阴影
    if shadow_color:
        draw.text((x+dx, y+dy), text, font=font, fill=shadow_color)
    # 描边
    if outline_color:
        for ox in [-1,0,1]:
            for oy in [-1,0,1]:
                if ox !=0 or oy !=0:
                    draw.text((x+ox, y+oy), text, font=font, fill=outline_color)
    # 主文字
    draw.text((x, y), text, font=font, fill=fill)

def create_gradient_overlay(width, height, start_alpha=120, end_alpha=300, gradient_height_percent=0.45):
    """创建图片底部渐变遮罩"""
    gradient = Image.new('RGBA', (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(gradient)
    gradient_height = int(height * gradient_height_percent)
    gradient_start = height - gradient_height

    for y in range(gradient_start, height):
        progress = (y - gradient_start) / gradient_height
        alpha = int(start_alpha + (end_alpha - start_alpha) * progress)
        draw.rectangle([(0, y), (width, y+1)], fill=(0,0,0,alpha))
    return gradient

# ==================== 核心业务函数 ====================
def translate_with_api(text):
    """调用 API 翻译文本并生成标题"""
    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": API_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": """你是资深国际政治新闻编辑，精通中美双语，生成20-35字中文标题，符合40岁以上男性喜好，硬朗简练，无额外字符。"""
                },
                {"role": "user", "content": text}
            ]
        }
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"翻译失败: {e}")
        return text  # 失败时返回原文

def cover_making(image_path, output_path, translated_text):
    """生成带翻译文字的封面（核心功能）"""
    try:
        # 打开背景图并添加渐变遮罩
        background = Image.open(image_path).convert('RGBA')
        width, height = background.size
        gradient_overlay = create_gradient_overlay(width, height)
        background = Image.alpha_composite(background, gradient_overlay)
        draw = ImageDraw.Draw(background)

        # 加载字体（适配系统字体）
        try:
            font_text = ImageFont.truetype(FONT_PATH, 150)
            font_bilingual = ImageFont.truetype(FONT_PATH, 50)
        except IOError:
            font_text = ImageFont.load_default(size=150)
            font_bilingual = ImageFont.load_default(size=50)
            print(f"字体加载失败，使用默认字体: {FONT_PATH}")

        # 绘制右上角"中英双语"
        text_cn_en = "中英双语"
        text_cn_en_bbox = draw.textbbox((0,0), text_cn_en, font=font_bilingual)
        text_cn_en_position = (width - 50 - text_cn_en_bbox[2], 30)
        draw_text_with_effects(draw, text_cn_en, text_cn_en_position, font_bilingual, fill="white")

        # 绘制翻译标题（自动换行+字体自适应）
        if translated_text:
            text_area_width = width - 100
            text_start_y = height * 0.5
            font_size = 150

            # 动态调整字体大小
            while font_size > 65:
                font = ImageFont.truetype(FONT_PATH, font_size) if os.path.exists(FONT_PATH) else ImageFont.load_default(size=font_size)
                lines = wrap_text(translated_text, font, text_area_width)[:3]  # 最多3行
                line_height = font.getbbox("测")[3] + 15
                total_height = len(lines) * line_height
                if total_height <= (height - text_start_y) * 0.8:
                    break
                font_size -= 5

            # 居中绘制文字
            font = ImageFont.truetype(FONT_PATH, font_size) if os.path.exists(FONT_PATH) else ImageFont.load_default(size=font_size)
            lines = wrap_text(translated_text, font, text_area_width)[:3]
            line_height = font.getbbox("测")[3] + 15
            total_height = len(lines) * line_height
            start_y = text_start_y + (height - text_start_y - total_height) // 2
            text_color = random.choice(COLOR_LIST)

            for i, line in enumerate(lines):
                line_width = font.getlength(line)
                x = (width - line_width) // 2
                y = start_y + i * line_height
                draw_text_with_effects(draw, line, (x, y), font, fill=text_color)

        # 保存封面
        background.convert('RGB').save(output_path)
        print(f"封面生成成功: {output_path}")
    except Exception as e:
        print(f"封面生成失败: {e}")

def generate_publish_times(video_count):
    """生成发布时间戳（UTC+8）"""
    utc8 = timezone(timedelta(hours=8))
    start_date = datetime.now(utc8).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    publish_times = []
    day = 0
    while len(publish_times) < video_count:
        current_date = start_date + timedelta(days=day)
        publish_times.extend([
            current_date.replace(hour=8, minute=0),
            current_date.replace(hour=9, minute=30)
        ])
        day += 1
    return [int(time.timestamp()) for time in publish_times[:video_count]]

def create_yaml_config(videos, covers, titles, dtimes, yaml_file=YAML_OUTPUT_FILE):
    """生成最终 YAML 配置文件"""
    desc_text = """本频道分享中英双语时事内容，为英语学习提供素材。内容仅供交流，不代表任何立场。感谢点赞关注充电支持！"""
    data = {
        "submit": "App",
        "limit": 3,
        "streamers": {
            video: {
                "copyright": 1,
                "no_reprint": 1,
                "tid": 208,
                "cover": cover,
                "title": title,
                "desc": desc_text,
                "tag": TAG,
                "dtime": dtime,
                "open-elec": 1
            } for video, cover, title, dtime in zip(videos, covers, titles, dtimes)
        }
    }
    with open(yaml_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"YAML 配置生成成功: {yaml_file}")

# ==================== 主函数 ====================
def main():
    # 1. 查找文件
    covers = find_files_with_suffix(OUTPUT_DIR, COVER_SUFFIX)
    videos = find_files_with_suffix(OUTPUT_DIR, 'output_sub.mp4')
    if not covers or not videos:
        print("未找到封面或视频文件")
        return

    # 2. 生成发布时间
    dtimes = generate_publish_times(len(videos))

    # 3. 翻译标题 + 生成封面
    titles, new_covers = [], []
    for video, cover in tqdm(zip(videos, covers), desc="处理中"):
        # 获取文件夹名作为翻译素材
        folder_name = os.path.basename(os.path.dirname(video))
        translated_title = translate_with_api(folder_name)
        titles.append(f"【双语】{translated_title} | {datetime.now().strftime('%m-%d')}")
        print(translated_title)
        # 生成新封面
        new_cover_name = os.path.basename(cover).replace(COVER_SUFFIX, NEW_COVER_SUFFIX)
        new_cover_path = os.path.join(os.path.dirname(cover), new_cover_name)
        cover_making(cover, new_cover_path, translated_title)
        new_covers.append(new_cover_path)

    # 4. 生成 YAML 配置
    create_yaml_config(videos, new_covers, titles, dtimes)

if __name__ == "__main__":
    main()

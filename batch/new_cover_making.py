import os
import shutil
import json
import random
import yaml
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from tqdm import tqdm
from fuzzywuzzy import fuzz

# ==================== 全局配置 ====================
OUTPUT_DIR = 'output'
COVER_SUFFIX = '.jpg'
NEW_COVER_SUFFIX = '_new.png'
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TAG = '每日英语新闻, 英语新闻, 英语学习, 川普, 马斯克, 咨询直通车, 社会观察局, 热点深度观察'

# API 配置 (保持你的配置)
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai'
API_MODEL = 'gemini-2.5-flash-lite-preview-09-2025'

def get_font_path():
    possible_fonts = [
        "/root/VideoLingo/batch/Fonts/HYWenHei-65W.ttf"
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "SourceHanSansSC-Bold.otf",
        "SimHei.ttf",
        "arial.ttf"
    ]
    for fp in possible_fonts:
        if os.path.exists(fp): return fp
    return "arial.ttf"

FONT_PATH = get_font_path()

# ==================== 核心改进：封面设计函数 ====================

def wrap_text_styled(text, font, max_width):
    """更智能的换行，确保不会切断关键词"""
    lines = []
    current_line = ""
    for char in text:
        if font.getlength(current_line + char) <= max_width:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    lines.append(current_line)
    return lines[:2]  # 新闻封面建议最多2行，保持视觉冲击力

import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import random
# ==================== 配置中心 ====================
# 扩充热词库，包含你图片中出现的关键词
HOT_KEYWORDS = ["川普", "特朗普", "马斯克", "美方", "委内瑞拉", "中方", "危机", "内幕", "拜登"]
HIGHLIGHT_COLOR = "#FFD700"  # 品牌黄
NORMAL_COLOR = "#FFFFFF"     # 纯白
BG_BOX_COLOR = (0, 0, 0, 230) # 接近全黑的深色半透明
RED_ACCENT = "#E21918"       # 新闻红

def get_font(size):
    # 这里建议确保 FONT_PATH 指向一个粗体中文字体
    from __main__ import FONT_PATH
    return ImageFont.truetype(FONT_PATH, size)

# ==================== 核心逻辑：精准对齐与高亮 ====================

def draw_text_line_centered(draw, line, font, x_start, y_top, box_height):
    """
    在指定的 y 轴范围内，让文字在黑框中垂直居中并处理高亮
    """
    # 1. 计算文字实际占用的高度 (避开字体渲染产生的多余空白)
    left, top, right, bottom = font.getbbox(line)
    text_width = right - left
    text_height = bottom - top
    
    # 2. 计算垂直居中的偏移量
    # y_top 是黑框的顶部，y_offset 让文字视觉中心与黑框中心对齐
    vertical_center_offset = (box_height - text_height) // 2 - top
    draw_y = y_top + vertical_center_offset

    # 3. 处理高亮逻辑
    current_x = x_start
    words_to_draw = []
    
    # 简单的分词高亮逻辑：扫描关键词
    temp_line = line
    while temp_line:
        found = False
        for kw in HOT_KEYWORDS:
            if temp_line.startswith(kw):
                words_to_draw.append((kw, HIGHLIGHT_COLOR))
                temp_line = temp_line[len(kw):]
                found = True
                break
        if not found:
            # 取第一个字符作为普通文字
            char = temp_line[0]
            if words_to_draw and words_to_draw[-1][1] == NORMAL_COLOR:
                words_to_draw[-1] = (words_to_draw[-1][0] + char, NORMAL_COLOR)
            else:
                words_to_draw.append((char, NORMAL_COLOR))
            temp_line = temp_line[1:]

    # 4. 执行绘制
    for text_part, color in words_to_draw:
        draw.text((current_x, draw_y), text_part, font=font, fill=color)
        current_x += font.getlength(text_part)

def cover_making_v4(image_path, output_path, translated_text):
    TARGET_WIDTH, TARGET_HEIGHT = 1920, 1080
    try:
        # 1. 底图处理 (背景虚化 + 暗角)
        bg = Image.open(image_path).convert('RGBA')
        bg = bg.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=2)) 
        overlay = Image.new('RGBA', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 50))
        canvas = Image.alpha_composite(bg, overlay)
        draw = ImageDraw.Draw(canvas)

        # 2. 顶部红色标签 (固定位置，避免 Overlap)
        tag_font = get_font(45)
        tag_text = " 🌐 GLOBAL NEWS • 深度直击 "
        tag_w = tag_font.getlength(tag_text)
        draw.rectangle([0, 60, tag_w + 100, 130], fill=RED_ACCENT)
        draw.text((50, 72), tag_text, font=tag_font, fill="white")

        # 3. 标题排版
        title_size = 140
        title_font = get_font(title_size)
        clean_title = translated_text.split(']')[-1] if ']' in translated_text else translated_text
        
        # 换行处理
        #from __main__ import wrap_text
        lines = wrap_text_styled(clean_title, title_font, TARGET_WIDTH - 300)[:2]

        # 4. 动态计算黑框和文字位置
        box_h = title_size + 40  # 给文字上下留出 20px 的空间
        margin_bottom = 120      # 距离底部距离
        total_h = len(lines) * (box_h + 20) # 包含行间距
        
        # 起始 Y 坐标（确保不遮挡顶部）
        current_y = max(TARGET_HEIGHT - total_text_height - margin_bottom, 200)

        for line in lines:
            line_w = title_font.getlength(line)
            # 黑框范围：左侧留出 60px 边距
            box_left = 60
            box_right = box_left + line_w + 80 # 左右 Padding 共 80px
            
            # 绘制黑框背景
            draw.rectangle([box_left, current_y, box_right, current_y + box_h], fill=BG_BOX_COLOR)
            # 绘制左侧装饰红杠 (宽度 15px)
            draw.rectangle([box_left, current_y, box_left + 15, current_y + box_h], fill=RED_ACCENT)
            
            # 在黑框内绘制垂直居中的高亮文字
            draw_text_line_centered(draw, line, title_font, box_left + 40, current_y, box_h)
            
            current_y += box_h + 25 # 下移并增加行间距

        # 5. 保存结果
        canvas.convert('RGB').save(output_path, quality=95)
        print(f"✨ 封面已保存（精准对齐版）: {output_path}")

    except Exception as e:
        print(f"❌ 封面失败: {e}")

# ==================== 其他工具函数 (保持并微调) ====================

def translate_with_api(text: str) -> str:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    prompt = "你是一名资深国际政治编辑。任务：基于英文内容生成一条符合40岁以上男性喜好的中文标题，格式为：[频道名]标题。仅输出一行文本，字数15字左右，关键词前置，具有冲击力。"
    data = {
        "model": API_MODEL,
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}],
    }
    try:
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data, timeout=30)
        return response.json()["choices"][0]["message"]["content"].strip()
    except:
        return None

def create_yaml_config(videos, covers, titles, dtimes, yaml_file, is_paid=False):
    desc = "深度国际时事解读，中英双语精校。内容仅供学习交流，欢迎点赞关注支持！"
    streamers = {}
    for video, cover, title, dtime in zip(videos, covers, titles, dtimes):
        entry = {
            "copyright": 1, "source": None, "tid": 208, "cover": cover, "title": title,
            "desc": desc, "tag": TAG, "dtime": dtime, "open-elec": 1,
        }
        if is_paid:
            entry.update({"charging_pay": 1, "upower_level_id": "1212996740244948080"})
        streamers[video] = entry
    
    with open(yaml_file, 'w', encoding='utf-8') as f:
        yaml.dump({"submit": "App", "streamers": streamers}, f, allow_unicode=True, sort_keys=False)

# ==================== 主流程 ====================

def main():
    # 模拟获取文件
    covers = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(COVER_SUFFIX)]
    # 注意：这里为了方便你直接测，假设你的视频文件夹结构如常
    video_files = [] 
    for root, _, files in os.walk(OUTPUT_DIR):
        if 'output_sub.mp4' in files:
            video_files.append(os.path.join(root, 'output_sub.mp4'))

    if not video_files:
        print("❌ 未找到视频文件，请确保 output 目录下有 output_sub.mp4")
        return

    # 简化的时间生成
    now = datetime.now()
    dtimes = [int((now + timedelta(days=1, hours=i)).timestamp()) for i in range(len(video_files))]

    # 处理封面和标题
    translated_titles = []
    final_covers = []
    
    for vid_path in tqdm(video_files, desc="处理任务"):
        folder_name = os.path.basename(os.path.dirname(vid_path))
        raw_cover = os.path.join(os.path.dirname(vid_path), folder_name + COVER_SUFFIX)
        new_cover = raw_cover.replace(COVER_SUFFIX, NEW_COVER_SUFFIX)
        
        # 1. 翻译标题
        translated = translate_with_api(folder_name) or folder_name
        translated_titles.append(f"{translated} | 双语精校")
        
        # 2. 生成新封面
        if os.path.exists(raw_cover):
            cover_making_v4(raw_cover, new_cover, translated)
            final_covers.append(new_cover)
        else:
            print(f"⚠️ 找不到原封面: {raw_cover}")

    # 3. 生成 YAML
    if len(final_covers) == len(video_files):
        create_yaml_config(video_files, final_covers, translated_titles, dtimes, 'config_bili_pro.yaml')
        print("✨ 全部任务完成！")

if __name__ == "__main__":
    main()
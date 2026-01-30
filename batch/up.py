import os
import shutil
import json
import random
import yaml
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm
from fuzzywuzzy import fuzz

# ==================== 全局常量 ====================
OUTPUT_DIR = 'output'
COVER_SUFFIX = '.jpg'
VIDEO_SUFFIX = '.mp4'
NEW_COVER_SUFFIX = '_new.png'
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TAG = ['每日英语新闻, 英语新闻, 英语学习, 川普, 马斯克, 咨询直通车, 社会观察局, 热点深度观察']
YAML_OUTPUT_FILE = 'config_bili.yaml'
error_dir = os.path.join(OUTPUT_DIR, 'ERROR')

# API 配置
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai'  # ✅ 修复尾部空格
#API_MODEL = 'sophnet/DeepSeek-V3.2'
API_MODEL = 'gemini-2.5-flash-lite-preview-09-2025'
#API_MODEL = 'grok-4-1-fast-non-reasoning'
# 自动选择字体
def get_font_path():
    possible_fonts = [
        #"Fonts/HYWenHei-65W.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "arial.ttf"
    ]
    for fp in possible_fonts:
        if os.path.exists(fp):
            return fp
    return "arial.ttf"

FONT_PATH = get_font_path()
print(f"【字体】使用: {FONT_PATH}")

# ==================== 工具函数 ====================
def find_files_with_suffix(directory: str, suffix: str) -> list:
    return [
        os.path.join(root, file)
        for root, _, files in os.walk(directory)
        for file in files
        if file.endswith(suffix)
    ]

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

def draw_text_with_effects(draw, text, position, font, fill, outline_color="black", outline_width=4, shadow_color=None):
    x, y = position
    if shadow_color:
        draw.text((x + 4, y + 4), text, font=font, fill=shadow_color)
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
    draw.text((x, y), text, font=font, fill=fill)

def create_gradient_overlay(width, height, start_alpha=120, end_alpha=220, gradient_height_percent=0.45):
    gradient = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    grad_h = int(height * gradient_height_percent)
    start_y = height - grad_h
    for y in range(start_y, height):
        alpha = int(start_alpha + (end_alpha - start_alpha) * (y - start_y) / grad_h)
        alpha = max(0, min(255, alpha))
        draw.rectangle([(0, y), (width, y + 1)], fill=(0, 0, 0, alpha))
    return gradient

# ==================== API 与翻译 ====================
def translate_with_api(text: str) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    prompt = """
角色（Role）：
你是一名资深国际政治与军事新闻编辑，具备十年以上中美战略议题报道经验，精通美国政治话语体系、国防术语及舆论叙事逻辑，同时深谙中国主流媒体话语风格与受众心理。你擅长将西方信源转化为符合中国立场、兼具专业权威性与大众传播力的新闻标题。

任务（Task）：
基于提供的英文原始内容，提取频道名,生成一条符合中文新闻传播规律的单行标题，用于国内主流资讯平台发布。

核心目标（Objective）：
信息量大, 尽可能标题党，最大化点击率与用户共鸣，符合40岁以上男性喜好的风格, 标题字数控制在15字左右, 节奏紧凑，关键词前置
禁止添加解释、注释、引号或其他任何额外字符

输出规范（Output Specification）：
仅输出一行文本，格式为：[频道名]标题
"""
    data = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
    }
    try:
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"].strip()
        print(f"API 返回: {result}")
        return result
    except Exception as e:
        print(f"翻译失败: {e}")
        return None

# ==================== 文件处理 ====================
def simple_read_topic(file_path: str) -> list:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]

def find_channel_by_fuzzy_match(excel_path: str, target_title: str, min_similarity=80):
    try:
        df = pd.read_excel(excel_path)
        if 'title' not in df.columns or 'channel_name' not in df.columns:
            print("⚠️ Excel 缺少 'title' 或 'channel_name' 列")
            return None
        best_match, best_score = None, 0
        for _, row in df.iterrows():
            current_title = str(row['title'])
            similarity = fuzz.ratio(target_title.lower(), current_title.lower())
            if similarity > best_score and similarity >= min_similarity:
                best_score, best_match = similarity, row['channel_name']
        if best_match:
            print(f"✅ 最佳匹配（相似度 {best_score}%）：'{best_match}'")
            return best_match
        else:
            print(f"❌ 未找到 ≥{min_similarity}% 的匹配项")
            return None
    except Exception as e:
        print(f"❌ 匹配出错: {e}")
        return None

# ==================== 封面生成 ====================
def cover_making(image_path: str, output_path: str, translated_text: str):
    try:
        if not translated_text or not isinstance(translated_text, str):
            translated_text = os.path.basename(os.path.dirname(image_path))

        background = Image.open(image_path).convert('RGBA')
        orig_w, orig_h = background.size
        scale = min(TARGET_WIDTH / orig_w, TARGET_HEIGHT / orig_h)
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)
        background = background.resize((new_w, new_h), Image.Resampling.LANCZOS)

        canvas = Image.new('RGBA', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 255))
        paste_x = (TARGET_WIDTH - new_w) // 2
        paste_y = (TARGET_HEIGHT - new_h) // 2
        canvas.paste(background, (paste_x, paste_y))

        gradient = create_gradient_overlay(TARGET_WIDTH, TARGET_HEIGHT)
        canvas = Image.alpha_composite(canvas, gradient)
        draw = ImageDraw.Draw(canvas)

        # === 中英双语标签 ===
        try:
            font_bilingual = ImageFont.truetype(FONT_PATH, 50)
            text_tag = "中英双语"
            bbox = draw.textbbox((0, 0), text_tag, font=font_bilingual)
            x_tag = TARGET_WIDTH - 50 - (bbox[2] - bbox[0])
            y_tag = 30
            draw_text_with_effects(
                draw, text_tag, (x_tag, y_tag), font_bilingual,
                fill="white", outline_color="black", outline_width=2
            )
        except Exception as e:
            print(f"⚠️ 中英双语标签失败: {e}")

        # === 自适应标题（关键增强）===
        max_width = TARGET_WIDTH - 120
        GRADIENT_PERCENT = 0.45
        gradient_start_y = int(TARGET_HEIGHT * (1 - GRADIENT_PERCENT))
        gradient_height = TARGET_HEIGHT - gradient_start_y
        bottom_margin = 50
        usable_height = gradient_height - bottom_margin

        min_font_size = 40
        max_font_size = 180
        final_font = None
        lines = []

        for fs in range(max_font_size, min_font_size - 1, -2):
            try:
                font = ImageFont.truetype(FONT_PATH, fs)
            except:
                font = ImageFont.load_default()

            candidate = wrap_text(translated_text, font, max_width)
            if len(candidate) > 3:
                candidate = candidate[:3]
                while len(candidate[2]) > 0 and font.getlength(candidate[2] + "...") > max_width:
                    candidate[2] = candidate[2][:-1]
                candidate[2] += "..."

            # compute height
            try:
                bbox = font.getbbox("测")
                line_h = (bbox[3] - bbox[1]) + 12
            except:
                line_h = int(fs * 1.2)
            total_h = len(candidate) * line_h

            if total_h <= usable_height:
                final_font = font
                lines = candidate
                break

        if final_font is None:
            final_font = ImageFont.truetype(FONT_PATH, min_font_size)
            lines = wrap_text(translated_text, final_font, max_width)[:3]
            if lines and len(lines[-1]) > 0:
                while len(lines[-1]) > 0 and final_font.getlength(lines[-1] + "...") > max_width:
                    lines[-1] = lines[-1][:-1]
                lines[-1] += "..."

        # === 计算位置 ===
        try:
            bbox = final_font.getbbox("测")
            line_height = (bbox[3]- bbox[1]) + 12
        except:
            line_height = 60
        total_h = len(lines) * line_height

        if total_h > usable_height:
            start_y = gradient_start_y + 10
        else:
            start_y = gradient_start_y + (usable_height - total_h) // 2

        text_color = random.choice([
            "#FF1493", "#FFD700", "#FF6347", "#00BFFF", "#32CD32", "#FF4500"
        ])

        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=final_font)
            x = (TARGET_WIDTH - (bbox[2] - bbox[0])) // 2
            y = start_y + i * line_height
            draw_text_with_effects(
                draw, line, (x, y), final_font,
                fill=text_color,
                outline_color="black",
                outline_width=4,
                shadow_color=(0, 0, 0, 180)
            )

        canvas.convert('RGB').save(output_path)
        print(f"✅ 保存封面: {output_path}")

    except Exception as e:
        import traceback
        print(f"❌ 封面失败 {image_path}: {e}")
        traceback.print_exc()

# ==================== 其余函数（保持不变） ====================
def send_wechat_notification(free_count, paid_count, titles):
    SENDKEY = "SCT294207T8J9Mnz8j7lAfG23gPWHT1FZD"
    if not SENDKEY or SENDKEY == "YOUR_SENDKEY_HERE":
        print("警告: 未配置 Server酱 SendKey，跳过微信推送。")
        return
    title = "YAML 生成完成"
    desc_parts = [f"已成功生成 YAML 配置文件！\n免费内容: {free_count} 个\n付费内容: {paid_count} 个\n\n--- 生成的标题列表 ---"]
    for i, t in enumerate(titles, 1):
        desc_parts.append(f"{i}. {t}")
    desc_text = "\n".join(desc_parts)
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"  # ✅ 修复 URL 空格
    params = {"title": title, "desp": desc_text}
    try:
        response = requests.post(url, data=params, timeout=10)
        if response.json().get("code") == 0:
            print("✅ 微信推送成功！")
        else:
            print(f"❌ 微信推送失败: {response.json().get('message')}")
    except Exception as e:
        print(f"❌ 微信推送异常: {e}")

def generate_titles(video_paths: list) -> tuple:
    titles, translated_texts = [], []
    excel_path = 'tasks_setting.xlsx'
    for video_path in video_paths:
        folder_name = os.path.basename(os.path.dirname(video_path))
        json_path = os.path.join('output', folder_name, 'gpt_log', 'summary.json')
        topic_list = simple_read_topic(json_path)
        channel_name = find_channel_by_fuzzy_match(excel_path, folder_name)
        content = f"频道名为：{channel_name} 标题为:{folder_name} 主题为:{topic_list}"
        translated = translate_with_api(content) or folder_name
        translated_texts.append(translated)
        month_day = datetime.now().strftime("%m-%d")
        full_title = f"{translated} | 双语精校 | 每日新闻 "
        titles.append(full_title)
        print(full_title)
    return titles, translated_texts

def timed_published(videos: list) -> list:
    video_count = len(videos)
    days_needed = (video_count // 2) + (1 if video_count % 2 else 0)
    utc8 = timezone(timedelta(hours=8))
    start_date = datetime.now(utc8).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    publish_times = []
    for day in range(days_needed):
        d = start_date + timedelta(days=day)
        publish_times.extend([d.replace(hour=8, minute=0), d.replace(hour=9, minute=30)])
    timestamps = [int(t.timestamp()) for t in publish_times]
    return timestamps[:video_count]

def create_yaml_config(videos, covers, titles, dtimes, yaml_file, is_paid=False):
    desc = (
        "本频道致力于分享中英双语的时事内容、热点解读与观点碰撞。\n"
        "我们希望用更平易近人的方式，一起了解世界，也能为英语学习提供真实有料的素材。\n"
        "内容仅供学习与交流，请勿过度解读，更不代表任何立场。观点多元，欢迎理性讨论！\n"
        "视频素材来自公开网络与授权资源，如有侵权请私信或留言联系删除。\n"
        "如果觉得频道还不错，拜托动动手：点赞、投币、收藏，顺手点个关注！\n"
        "更希望得到大家的【充电支持】，这是我们持续更新的最大动力！\n\n"
    )
    streamers = {}
    for video, cover, title, dtime in zip(videos, covers, titles, dtimes):
        entry = {
            "copyright": 1,
            "no_reprint": 1,
            "source": None,
            "tid": 208,
            "cover": cover,
            "title": title,
            "desc_format_id": 0,
            "topic_id": 1167972,
            "topic_detail": {"from_topic_id": 1167972, "from_source": "arc.web.recommend"},
            "desc": desc,
            "dolby": 1,
            "lossless_music": 1,
            "tag": TAG[0],
            "dynamic": "",
            "dtime": None,
            "open-elec": 1,
        }
        if is_paid:
            entry.update({
                "charging_pay": 1,
                "preview": {"need_preview": 1, "start_time": 0, "end_time": 2},
                "upower_level_id": "1212996740244948080",
                "upower_mode": 0,
                "upower_unit_price": 0,
            })
        streamers[video] = entry
    data = {"submit": "App", "streamers": streamers}
    with open(yaml_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"✅ YAML 已保存: {yaml_file}")

def split_and_create_yaml(videos, covers, titles, dtimes, paid_ratio=0.3):
    total = len(videos)
    indices = list(range(total))
    random.shuffle(indices)
    split_point = int(total * (1 - paid_ratio))
    free_idx = indices[:split_point]
    paid_idx = indices[split_point:]
    create_yaml_config([videos[i] for i in free_idx], [covers[i] for i in free_idx],
                       [titles[i] for i in free_idx], dtimes, 'free_content.yaml', is_paid=False)
    create_yaml_config([videos[i] for i in paid_idx], [covers[i] for i in paid_idx],
                       [titles[i] for i in paid_idx], dtimes, 'paid_content.yaml', is_paid=True)

def find_output_with_sub_files(directory: str) -> list:
    return [
        os.path.join(root, file)
        for root, _, files in os.walk(directory)
        for file in files
        if file == 'output_sub.mp4'
    ]

# ==================== 主程序 ====================
def main():
    if os.path.exists(error_dir):
        shutil.rmtree(error_dir)
        print(f"已清理 {error_dir}")

    covers = find_files_with_suffix(OUTPUT_DIR, COVER_SUFFIX)
    videos = find_output_with_sub_files(OUTPUT_DIR)
    #videos = videos[0:2]
    if not videos:
        print("❌ 未找到任何视频文件")
        return

    dtimes = timed_published(videos)
    titles, translated_texts = generate_titles(videos)

    for cover, translated in tqdm(zip(covers, translated_texts), total=len(covers), desc="生成封面"):
        cover_dir = os.path.dirname(cover)
        new_name = os.path.basename(cover).replace(COVER_SUFFIX, NEW_COVER_SUFFIX)
        output_path = os.path.join(cover_dir, new_name)
        clean_translated = translated.split('‖')[0] if translated else cover_dir
        cover_making(cover, output_path, clean_translated)

    new_covers = find_files_with_suffix(OUTPUT_DIR, NEW_COVER_SUFFIX)
    assert len(new_covers) == len(videos) == len(titles), "文件数量不一致！"

    paid_ratio = 0.1
    total_videos = len(videos)
    paid_count = int(total_videos * paid_ratio)
    free_count = total_videos - paid_count
    split_and_create_yaml(videos, new_covers, titles, dtimes, paid_ratio=paid_ratio)
    send_wechat_notification(free_count, paid_count, translated_texts)

if __name__ == "__main__":
    main()

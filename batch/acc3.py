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
FONT_PATH = "Fonts\\msyhbd.ttc"  # 微软雅黑粗体
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720
TAG = ['英语新闻, 英语学习, 川普, 马斯克, 咨询直通车, 社会观察局, 热点深度观察']
YAML_OUTPUT_FILE = 'config_bili.yaml'
error_dir = os.path.join(OUTPUT_DIR, 'ERROR')

# API 配置（修复多余空格）
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai' # 修复了多余的空格
API_MODEL = 'glm-4.7'


# ==================== 工具函数 ====================
def find_files_with_suffix(directory: str, suffix: str) -> list:
    """递归查找指定后缀的文件"""
    return [
        os.path.join(root, file)
        for root, _, files in os.walk(directory)
        for file in files
        if file.endswith(suffix)
    ]


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """中文友好文本自动换行"""
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


def draw_text_with_effects(draw, text, position, font, fill, outline_color=None, shadow_color=None, shadow_offset=(3, 3)):
    """绘制带阴影和轮廓的文字"""
    x, y = position
    dx, dy = shadow_offset

    if shadow_color:
        draw.text((x + dx, y + dy), text, font=font, fill=shadow_color)

    if outline_color:
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                if ox != 0 or oy != 0:
                    draw.text((x + ox, y + oy), text, font=font, fill=outline_color)

    draw.text((x, y), text, font=font, fill=fill)


def create_gradient_overlay(width, height, start_alpha=120, end_alpha=300, gradient_height_percent=0.45):
    """创建底部渐变遮罩（用于文字背景）"""
    gradient = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    gradient_height = int(height * gradient_height_percent)
    gradient_start = height - gradient_height

    for y in range(gradient_start, height):
        progress = (y - gradient_start) / gradient_height
        alpha = int(start_alpha + (end_alpha - start_alpha) * progress)
        draw.rectangle([(0, y), (width, y + 1)], fill=(0, 0, 0, alpha))
    return gradient


# ==================== API 与翻译 ====================
def translate_with_api(text: str) -> str:
    """调用 302.ai API 生成中文新闻标题"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    prompt = """
角色（Role）：
你是一名资深国际政治与军事新闻编辑，具备十年以上中美战略议题报道经验，精通美国政治话语体系、国防术语及舆论叙事逻辑，同时深谙中国主流媒体话语风格与受众心理。你擅长将西方信源转化为符合中国立场、兼具专业权威性与大众传播力的新闻标题。

任务（Task）：
基于提供的英文原始内容，生成一条符合中文新闻传播规律的单行标题，用于国内主流资讯平台发布。

核心目标（Objective）：
可以标题党，最大化点击率与用户共鸣，符合40岁以上男性喜好的风格, 标题字数控制在20–35字之间，节奏紧凑，关键词前置
禁止添加解释、注释、引号或其他任何额外字符

输出规范（Output Specification）：
仅输出一行文本，格式为：标题
"""
    data = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
    }

    try:
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"].strip()
        print(f"API 返回: {result}")
        return result
    except Exception as e:
        print(f"翻译失败: {e}")
        return None


# ==================== 文件处理 ====================
def simple_read_topic(file_path: str) -> list:
    """从 summary.json 读取 topic 字段"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]


def find_channel_by_fuzzy_match(excel_path: str, target_title: str, min_similarity=80):
    """模糊匹配 Excel 中的 channel_name"""
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
    """在封面图上叠加标题和双语标识，并将其缩放至 1280x720"""
    try:
        # 1. 打开并缩放图像
        background = Image.open(image_path).convert('RGBA')
        original_width, original_height = background.size
        print(f"原始封面尺寸: {original_width}x{original_height}")

        # 计算缩放比例，以较短边为准，保证内容不被拉伸
        scale_w = TARGET_WIDTH / original_width
        scale_h = TARGET_HEIGHT / original_height
        scale = min(scale_w, scale_h)

        new_width = int(original_width * scale)
        new_height = int(original_height * scale)

        # 调整图像大小
        background = background.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 创建一个 1280x720 的新画布
        final_background = Image.new('RGBA', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 255))
        # 将缩放后的图像粘贴到新画布中心
        paste_x = (TARGET_WIDTH - new_width) // 2
        paste_y = (TARGET_HEIGHT - new_height) // 2
        final_background.paste(background, (paste_x, paste_y))

        # 2. 添加渐变遮罩
        gradient = create_gradient_overlay(TARGET_WIDTH, TARGET_HEIGHT)
        background = Image.alpha_composite(final_background, gradient)
        draw = ImageDraw.Draw(background)

        # 3. 绘制元素 (字体大小等也需要根据新尺寸调整)
        # 使用缩放后的尺寸来计算字体大小和位置
        # 例如，如果原尺寸是 1920x1080，字体是 55，那么在 1280x720 下可以按比例缩小
        font_bilingual_size = int(50 * (TARGET_HEIGHT / 1080))
        font_text_base_size = int(200 * (TARGET_HEIGHT / 1080))

        font_bilingual = ImageFont.truetype(FONT_PATH, font_bilingual_size)
        font_text = ImageFont.truetype(FONT_PATH, font_text_base_size)

        # 右上角“中英双语”
        text_cn_en = "中英双语"
        bbox = draw.textbbox((0, 0), text_cn_en, font=font_bilingual)
        pos = (TARGET_WIDTH - 50 - (bbox[2] - bbox[0]), 30)
        draw_text_with_effects(draw, text_cn_en, pos, font_bilingual, fill="white", outline_color="white", shadow_color="rgba(0,0,0,128)")

        # 标题文本（居中，最多3行）
        if translated_text:
            text_area_width = TARGET_WIDTH - 100
            text_start_y = TARGET_HEIGHT * 0.50
            font_size = font_text_base_size

            while font_size > int(65 * (TARGET_HEIGHT / 1080)): # 最小字体也按比例调整
                font_adj = ImageFont.truetype(FONT_PATH, font_size)
                lines = wrap_text(translated_text, font_adj, text_area_width)
                if len(lines) > 3:
                    lines = lines[:3]
                    if len(lines) == 3:
                        last = lines[2]
                        while font_adj.getlength(last + "...") > text_area_width and last:
                            last = last[:-1]
                        lines[2] = last + "..."

                line_height = font_adj.getbbox("测")[3] + int(15 * (TARGET_HEIGHT / 1080)) # 行间距也按比例调整
                total_height = len(lines) * line_height
                if total_height <= (TARGET_HEIGHT - text_start_y) * 0.8:
                    break
                font_size -= 5

            font_text = font_adj
            lines = wrap_text(translated_text, font_text, text_area_width)
            if len(lines) > 3:
                lines = lines[:3]
                if len(lines) == 3:
                    last = lines[2]
                    while font_text.getlength(last + "...") > text_area_width and last:
                        last = last[:-1]
                    lines[2] = last + "..."

            line_height = font_text.getbbox("测")[3] + int(15 * (TARGET_HEIGHT / 1080))
            total_height = len(lines) * line_height
            start_y = int(text_start_y + (TARGET_HEIGHT - text_start_y - total_height) // 2)

            text_color = random.choice([
                "#FF1493", "#FF69B4", "#FFD700", "#FF6347", "#00BFFF",
                "#32CD32", "#FF4500", "#9370DB", "#FF8C00", "#1E90FF"
            ])

            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font_text)
                x = (TARGET_WIDTH - (bbox[2] - bbox[0])) // 2
                y = start_y + i * line_height
                draw_text_with_effects(
                    draw, line, (x, y), font_text,
                    fill=text_color, outline_color="black",
                    shadow_color="rgba(0,0,0,180)", shadow_offset=(3, 3)
                )

        background.convert('RGB').save(output_path)
        print(f"✅ 保存封面 (1280x720): {output_path}")
    except IOError as e:
        print(f"❌ 封面处理失败 {image_path}: {e}")


# ==================== 标题与YAML生成 ====================
def generate_titles(video_paths: list) -> tuple:
    """为每个视频生成标题（基于文件夹名 + summary.json + channel 匹配）"""
    titles, translated_texts = [], []
    excel_path = r'E:\Bilinew\VideoLingo-main\batch\tasks_setting.xlsx'

    for video_path in video_paths:
        folder_name = os.path.basename(os.path.dirname(video_path))
        json_path = os.path.join('output', folder_name, 'gpt_log', 'summary.json')

        topic_list = simple_read_topic(json_path)
        channel_name = find_channel_by_fuzzy_match(excel_path, folder_name)

        content = f"频道名为：{channel_name} 标题为:{folder_name} 主题为:{topic_list}"
        translated = translate_with_api(content) or folder_name
        translated_texts.append(translated)

        month_day = datetime.now().strftime("%m-%d")
        full_title = f"【熟肉】 {translated} | {month_day}"
        titles.append(full_title)
        print(full_title)

    return titles, translated_texts


def timed_published(videos: list) -> list:
    """生成定时发布时间戳（UTC+8），每天 8:00 和 9:30"""
    video_count = len(videos)
    days_needed = (video_count // 2) + (1 if video_count % 2 else 0)
    utc8 = timezone(timedelta(hours=8))
    start_date = datetime.now(utc8).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    publish_times = []
    for day in range(days_needed):
        d = start_date + timedelta(days=day)
        publish_times.extend([
            d.replace(hour=8, minute=0),
            d.replace(hour=9, minute=30)
        ])

    timestamps = [int(t.timestamp()) for t in publish_times]
    return timestamps[:video_count]


def create_yaml_config(videos, covers, titles, dtimes, yaml_file, is_paid=False):
    """通用 YAML 生成函数（支持免费/付费）"""
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
            "dtime": None,  # 暂不启用定时
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

    data = {"submit": "app", "limit": 3, "streamers": streamers}
    try:
        with open(yaml_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        print(f"✅ YAML 已保存: {yaml_file}")
    except Exception as e:
        print(f"❌ YAML 保存失败: {e}")


def split_and_create_yaml(videos, covers, titles, dtimes, paid_ratio=0.3):
    """按比例拆分免费/付费内容"""
    total = len(videos)
    indices = list(range(total))
    random.shuffle(indices)
    split_point = int(total * (1 - paid_ratio))

    free_idx = indices[:split_point]
    paid_idx = indices[split_point:]

    create_yaml_config(
        [videos[i] for i in free_idx],
        [covers[i] for i in free_idx],
        [titles[i] for i in free_idx],
        dtimes,
        'free_content.yaml',
        is_paid=False
    )
    create_yaml_config(
        [videos[i] for i in paid_idx],
        [covers[i] for i in paid_idx],
        [titles[i] for i in paid_idx],
        dtimes,
        'paid_content.yaml',
        is_paid=True
    )


# ==================== 视频路径查找 ====================
def find_output_with_sub_files(directory: str) -> list:
    """查找 output_sub_final.mp4 文件"""
    return [
        os.path.join(root, file)
        for root, _, files in os.walk(directory)
        for file in files
        if file == 'output_sub_final.mp4'
    ]


# ==================== 主程序 ====================
def main():
    # 清理 ERROR 目录
    if os.path.exists(error_dir):
        shutil.rmtree(error_dir)
        print(f"已清理 {error_dir}")

    # 查找文件
    covers = find_files_with_suffix(OUTPUT_DIR, COVER_SUFFIX)
    videos = find_output_with_sub_files(OUTPUT_DIR)

    if not videos:
        print("❌ 未找到任何视频文件")
        return

    dtimes = timed_published(videos)
    titles, translated_texts = generate_titles(videos)

    # 生成新封面
    for cover, translated in tqdm(zip(covers, translated_texts), total=len(covers), desc="生成封面"):
        cover_dir = os.path.dirname(cover)
        new_name = os.path.basename(cover).replace(COVER_SUFFIX, NEW_COVER_SUFFIX)
        output_path = os.path.join(cover_dir, new_name)
        cover_making(cover, output_path, translated.split('‖')[0])

    # 重新扫描新封面
    new_covers = find_files_with_suffix(OUTPUT_DIR, NEW_COVER_SUFFIX)

    # 验证长度一致
    assert len(new_covers) == len(videos) == len(titles), "文件数量不一致！"

    # 生成 YAML（30% 付费）
    split_and_create_yaml(videos, new_covers, titles, dtimes, paid_ratio=0.3)


if __name__ == "__main__":
    main()
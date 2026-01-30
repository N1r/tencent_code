import os
import shutil
import json
import random
import yaml
import requests
import pandas as pd
import re
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from tqdm import tqdm
from fuzzywuzzy import fuzz  # 保持原代码的 fuzzywuzzy，也可以换成 rapidfuzz

# 尝试导入 jieba 进行智能名词识别
try:
    import jieba
    import jieba.posseg as pseg
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    print("🚩 提示：未安装 jieba，将使用基础随机逻辑。建议运行 'pip install jieba'")

# ==================== 全局常量与配置 ====================
OUTPUT_DIR = 'output'
COVER_SUFFIX = '.jpg'
NEW_COVER_SUFFIX = '_new.png'
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TAG = ['每日英语新闻, 英语新闻, 英语学习, 川普, 马斯克, 咨询直通车, 社会观察局, 热点深度观察']

# API 配置
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai'
#API_MODEL = 'gemini-2.5-flash-lite-preview-09-2025'
API_MODEL = 'qwen3-max-2026-01-23'
#API_MODEL = 'grok-4-1-fast-non-reasoning'
# 视觉规范
HIGHLIGHT_COLOR = "#FFD700"  # 品牌金黄
NORMAL_COLOR = "#FFFFFF"     # 纯白
BG_BOX_COLOR = (0, 0, 0, 230) # 黑色半透明背景块
RED_ACCENT = "#E21918"       # 标志性新闻红

# 自动选择字体
def get_font_path():
    possible_fonts = [
        "/root/VideoLingo/batch/Fonts/HYWenHei-65W.ttf",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "SourceHanSansSC-Bold.otf",
        "SimHei.ttf",
        "arial.ttf"
    ]
    for fp in possible_fonts:
        if os.path.exists(fp): return fp
    return "arial.ttf"

FONT_PATH = get_font_path()
print(f"【系统】使用字体: {FONT_PATH}")

# ==================== 0. 新增：信息提取工具 (来自代码2) ====================

def simple_read_topic(file_path: str) -> list:
    """读取 gpt_log 下的 summary.json 获取 topic"""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 兼容列表或字典结构
        if isinstance(data, list):
            return [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]
        elif isinstance(data, dict) and 'response' in data and 'topic' in data['response']:
             return [data['response']['topic']]
        return []
    except Exception as e:
        print(f"⚠️ 读取 Topic 失败: {e}")
        return []

def quick_read_srt(file_path: str) -> str:
    """极简读取 SRT 纯文本"""
    with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        content = f.read()
    
    # 匹配时间轴的正则
    pattern = r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}'
    
    # 一行搞定：过滤空行、数字行、时间行
    lines = [
        line.strip() for line in content.splitlines() 
        if line.strip() and not line.strip().isdigit() and not re.match(pattern, line)
    ]
    
    return "\n".join(lines)
def find_channel_by_fuzzy_match(excel_path: str, target_title: str, min_similarity=80):
    """根据文件夹名模糊匹配 Excel 中的频道名"""
    if not os.path.exists(excel_path):
        print(f"⚠️ 未找到 {excel_path}，跳过频道匹配")
        return None
    try:
        df = pd.read_excel(excel_path)
        if 'title' not in df.columns or 'channel_name' not in df.columns:
            print("⚠️ Excel 缺少 'title' 或 'channel_name' 列")
            return None
        
        best_match, best_score = None, 0
        for _, row in df.iterrows():
            current_title = str(row['title'])
            # 使用 fuzzywuzzy 的 ratio
            similarity = fuzz.ratio(target_title.lower(), current_title.lower())
            if similarity > best_score and similarity >= min_similarity:
                best_score, best_match = similarity, row['channel_name']
        
        if best_match:
            # print(f"✅ 频道匹配成功（{best_score}%）：'{best_match}'")
            return best_match
        else:
            return None
    except Exception as e:
        print(f"❌ 频道匹配出错: {e}")
        return None

# ==================== 1. 智能高亮逻辑 (避开虚词) ====================

def get_random_noun_highlight(text):
    """提取标题中的核心名词实体，避开虚词"""
    # 移除 [频道名] 干扰
    clean_text = re.sub(r'\[.*?\]', '', text)
    
    if HAS_JIEBA:
        words = pseg.cut(clean_text)
        nouns = [w.word for w in words if w.flag in ['n', 'nr', 'ns', 'nt', 'nz'] and len(w.word) > 1]
        if nouns:
            return random.choice(nouns)
    
    STOP_WORDS = ["的", "了", "在", "是", "被", "已经", "不仅", "甚至", "而且"]
    parts = re.findall(r'[\u4e00-\u9fa5]{2,4}', clean_text)
    valid_parts = [p for p in parts if p not in STOP_WORDS]
    
    return random.choice(valid_parts) if valid_parts else None

# ==================== 2. 封面绘图核心 (精准对齐) ====================

def wrap_text_styled(text, font, max_width):
    lines = []
    current_line = ""
    for char in text:
        if font.getlength(current_line + char) <= max_width:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    lines.append(current_line)
    return lines[:2] 

def draw_text_line_centered(draw, line, font, x_start, y_top, box_height, highlight_word):
    left, top, right, bottom = font.getbbox(line)
    text_height = bottom - top
    vertical_center_offset = (box_height - text_height) // 2 - top
    draw_y = y_top + vertical_center_offset

    if not highlight_word or highlight_word not in line:
        draw.text((x_start, draw_y), line, font=font, fill=NORMAL_COLOR)
        return

    parts = line.split(highlight_word, 1)
    current_x = x_start
    draw.text((current_x, draw_y), parts[0], font=font, fill=NORMAL_COLOR)
    current_x += font.getlength(parts[0])
    draw.text((current_x, draw_y), highlight_word, font=font, fill=HIGHLIGHT_COLOR)
    current_x += font.getlength(highlight_word)
    draw.text((current_x, draw_y), parts[1], font=font, fill=NORMAL_COLOR)

def cover_making(image_path, output_path, translated_text):
    try:
        hl_word = get_random_noun_highlight(translated_text)
        clean_title = re.sub(r'\[.*?\]', '', translated_text)

        bg = Image.open(image_path).convert('RGBA')
        bg = bg.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
        overlay = Image.new('RGBA', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 60))
        canvas = Image.alpha_composite(bg, overlay)
        draw = ImageDraw.Draw(canvas)

        tag_font = ImageFont.truetype(FONT_PATH, 45)
        tag_text = " 🌐 GLOBAL NEWS • 深度直击 "
        tag_w = tag_font.getlength(tag_text)
        draw.rectangle([0, 60, tag_w + 100, 135], fill=RED_ACCENT)
        draw.text((50, 75), tag_text, font=tag_font, fill="white")

        title_size = 140
        title_font = ImageFont.truetype(FONT_PATH, title_size)
        lines = wrap_text_styled(clean_title, title_font, TARGET_WIDTH - 300)

        box_h = title_size + 45
        line_spacing = 30
        total_h = len(lines) * box_h + (len(lines)-1) * line_spacing
        current_y = max(TARGET_HEIGHT - total_h - 130, 220)

        for line in lines:
            lw = title_font.getlength(line)
            box_l, box_r = 60, 60 + lw + 100
            draw.rectangle([box_l, current_y, box_r, current_y + box_h], fill=BG_BOX_COLOR)
            draw.rectangle([box_l, current_y, box_l + 15, current_y + box_h], fill=RED_ACCENT)
            draw_text_line_centered(draw, line, title_font, box_l + 45, current_y, box_h, hl_word)
            current_y += box_h + line_spacing

        canvas.convert('RGB').save(output_path, quality=95)
    except Exception as e:
        print(f"❌ 封面失败 {image_path}: {e}")

# ==================== 3. API 翻译逻辑 (已增强) ====================
#2.  必须包含【频道名】作为信源背书或嘲讽对象（如：MeidasTouch曝猛料 / 福克斯翻车）。

def translate_with_api(text_content: str) -> str:
    """
    接收包含 频道名、原标题、Topic 的综合字符串进行处理
    """
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    prompt = """
# Role

你是一名追求“高信息密度”的B站国际时政区资深编辑。你的核心能力是“降噪”：从冗长的外媒字幕中，提炼出最具体、最反直觉、或最具细节感的逻辑链条，而非简单的概括。
# Input Data

- 原标题：{folder_name}
- 讨论主题：{topic_list}
- 字幕内容：{srt_list}

# Construction Rules (核心修改点)

1. **拒绝笼统，必须具体（Granularity）：**

   - ❌ 错误：痛斥特朗普的政策很荒谬
   - ✅ 正确：吐槽特朗普“吸管治国”：为了省水把发型都洗塌了
   - **指令**：必须从字幕中提取**具体的名词、数据、比喻或特定事件**进标题。
2. **格式规范：**

   - 格式: 具象化细节/核心逻辑/经典语句.
   - 仅输出一行，严禁半角符号（: / \ ? * " < > |），字数25-35字。

# Workflow
1. 分析字幕，找到最具争议或最犀利的一句话。
2. 输出结果。

# Output Goal

生成一个 **“看了标题就知道视频讲了什么具体事”** 的文件名，而不是笼统的标题党。
"""
    data = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text_content}
        ],
    }
    try:
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data, timeout=30)
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"API Error: {e}")
        return None

# ==================== 4. 业务处理逻辑 (整合了 Topic 和 Channel) ====================

def generate_titles(video_paths: list) -> tuple:
    titles, translated_texts = [], []
    
    print(f"🔍 开始生成标题，共 {len(video_paths)} 个视频...")
    
    for video_path in video_paths:
        folder_path = os.path.dirname(video_path)
        folder_name = os.path.basename(folder_path)
        
        # --- 整合逻辑开始 ---
        # 1. 获取 Topic
        json_path = os.path.join(folder_path, 'gpt_log', 'summary.json')
        topic_list = simple_read_topic(json_path)
        srt_path = os.path.join(folder_path, 'trans.srt')
        srt_list = quick_read_srt(srt_path)
        #print(srt_list)
        # 2. 获取 Channel Name
        channel_name = find_channel_by_fuzzy_match('tasks_setting.xlsx', folder_name) or "精选新闻"
        
        # 3. 构造发送给 API 的内容
        #prompt_content = f"频道名为：{channel_name}\n原标题为:{folder_name}\n内容主题为:{topic_list}完整字幕: {srt_list}"
        prompt_content = f"频道名为：{channel_name}\n原标题为:{folder_name}\n内容主题为:{topic_list}完整字幕: {srt_list}"

        # print(f"  > 处理: {folder_name} | 频道: {channel_name}")
        # --- 整合逻辑结束 ---

        # 调用 API
        translated = translate_with_api(prompt_content) or folder_name
        
        # 结果处理
        translated_texts.append(translated)
        clean_t = re.sub(r'\[.*?\]', '', translated)
        
        # 最终标题加上频道名后缀 (如果需要)
        final_title = f"[中英]{clean_t}"
        titles.append(final_title)
        
        print(f" ✅ 生成标题: {final_title}")

    return titles, translated_texts

# ==================== 配置：文案与标签 (嘲讽/吃瓜风格) ====================

# 简介模板库（随机抽取，保持新鲜感，避免查重）
DESC_TEMPLATES = [
    """【中英双语】带你看懂美式“民主”的翻车现场 🤡
👉 挖掘美媒内讧实录，直击两党“互咬”最前线。
🚫 拒绝西方滤镜，还原最真实的美国。
---------------------------------------
📢 声明：视频素材源自外网，仅供批判性研究与语言学习。
🔥 每日更新美帝荒诞事，喜欢请【点赞+投币】支持，这对我真的很重要！""",

    """⚡️ 高能预警：美式政坛大型“双标”与“破防”现场
不仅是英语听力素材，更是观察西方社会撕裂的绝佳窗口。
看懂王（川普）如何整活，看自由派如何无能狂怒。
---------------------------------------
💡 关注频道，每天三分钟，用吃瓜的心态看世界。
✨ 你的【一键三连】是更新的最大动力！""",

    """🇺🇸 欢迎来到“自由美利坚”的魔幻现实主义片场。
这里有最犀利的媒体吐槽，最直接的政客互怼。
中英双语字幕精校，确保你不错过每一个“名场面”。
---------------------------------------
🎯 核心看点：特朗普 | 共和党内乱 | 媒体揭秘
💬 评论区以此为据，欢迎各路大神指点江山。
❤️ 觉得有意思请长按点赞，感谢支持！"""
]

# 补充标签（高热度关键词）
EXTRA_TAGS = "特朗普,美国大选,共和党,民主党,美式笑话,双语字幕,听力,国际时事,吃瓜"

# ==================== 核心逻辑：YAML 生成 ====================

def split_and_create_yaml(videos, covers, titles, dtimes, paid_ratio=0.1):
    """
    将视频列表随机划分为免费/付费内容，并生成对应的上传 YAML 配置文件
    """
    total = len(videos)
    indices = list(range(total))
    random.shuffle(indices) # 打乱顺序
    
    # 计算分割点
    split_point = int(total * (1 - paid_ratio))
    
    # --- 内部函数：写入 YAML ---
    def write_yaml(sub_v, sub_c, sub_t, sub_dt, filename, is_paid):
        streamers = {}
        
        for i, (v, c, t, dt) in enumerate(zip(sub_v, sub_c, sub_t, sub_dt)):
            # 1. 随机选择简介模板
            base_desc = random.choice(DESC_TEMPLATES)
            
            # 2. 组合最终简介 (将标题放在第一行，利于 SEO 和用户快速预览)
            final_desc = f"► 本期看点：{t}\n\n{base_desc}"
            
            # 3. 处理标签 (合并 Global TAG 和 EXTRA_TAGS)
            # 假设全局 TAG[0] 是类似 "每日英语新闻,..." 的字符串
            base_tag = TAG[0] if (type(TAG) is list and len(TAG) > 0) else ""
            combined_tag = f"{base_tag},{EXTRA_TAGS}"
            
            # 去重、去空、限制数量 (B站限制标签数，通常取前12个)
            tag_list = list(set([x.strip() for x in combined_tag.split(',') if x.strip()]))
            final_tag = ",".join(tag_list[:12])

            # 4. 构造单个视频的配置项
            entry = {
                "copyright": 1,           # 1=自制 (翻译二创通常投自制)
                "source": None,           # 自制无需 source
                "tid": 208,               # 分区ID (208=资讯-环球/时政，请根据需要调整)
                "cover": c, 
                "title": t,
                "desc": final_desc,
                "tag": final_tag,
                "dtime": dt,              # 定时发布时间戳
                "open-elec": 1,           # 开启充电
            }
            
            # 如果是付费内容，添加付费字段
            if is_paid:
                entry.update({
                    "charging_pay": 1, 
                    "upower_level_id": "1212996740244948080" # 🔴 请确认这是您的充电计划 ID
                })
                
            streamers[v] = entry

        # 5. 写入文件
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                # allow_unicode=True 保证中文正常显示，sort_keys=False 保持字段顺序
                yaml.dump({"submit": "App", "streamers": streamers}, f, allow_unicode=True, sort_keys=False)
            print(f"📄 已生成配置文件: {filename} (包含 {len(sub_v)} 个视频)")
        except Exception as e:
            print(f"❌ 写入 YAML 失败 ({filename}): {e}")

    # --- 执行分割与写入 ---
    
    # 划分索引
    f_idx = indices[:split_point] # 免费部分索引
    p_idx = indices[split_point:] # 付费部分索引
    
    # 生成免费内容的 YAML
    write_yaml(
        [videos[i] for i in f_idx], 
        [covers[i] for i in f_idx], 
        [titles[i] for i in f_idx], 
        [dtimes[i] for i in f_idx], 
        'free_content.yaml', 
        False
    )
    
    # 生成付费内容的 YAML (如果有的话)
    if p_idx:
        write_yaml(
            [videos[i] for i in p_idx], 
            [covers[i] for i in p_idx], 
            [titles[i] for i in p_idx], 
            [dtimes[i] for i in p_idx], 
            'paid_content.yaml', 
            True
        )
# ==================== 5. 主程序 ====================

def main():
    # 查找视频
    videos = []
    for root, _, files in os.walk(OUTPUT_DIR):
        if 'output_sub.mp4' in files:
            videos.append(os.path.join(root, 'output_sub.mp4'))
    
    if not videos:
        print("❌ 未发现 output_sub.mp4 文件")
        return

    # 1. 标题与翻译 (核心逻辑已更新)
    bilibili_titles, translated_raw = generate_titles(videos)
    
    # 2. 定时发布时间 (明天开始，每隔1.5小时一个)
    start_time = datetime.now(timezone(timedelta(hours=8))).replace(hour=8, minute=0, second=0) + timedelta(days=1)
    dtimes = [int((start_time + timedelta(minutes=45*i)).timestamp()) for i in range(len(videos))]

    # 3. 处理封面
    new_covers = []
    for vid, trans in tqdm(zip(videos, translated_raw), total=len(videos), desc="生成封面"):
        folder = os.path.dirname(vid)
        # 寻找原图
        raw_jpg = next((os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.jpg')), None)
        if raw_jpg:
            new_c = raw_jpg.replace('.jpg', NEW_COVER_SUFFIX)
            cover_making(raw_jpg, new_c, trans)
            new_covers.append(new_c)
        else:
            new_covers.append("") # 占位

    # 4. 生成 YAML
    split_and_create_yaml(videos, new_covers, bilibili_titles, dtimes)
    print("✨ 全部流程完成，YAML 已生成。")

if __name__ == "__main__":
    main()

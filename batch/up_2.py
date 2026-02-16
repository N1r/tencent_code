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

import re
from PIL import Image, ImageFilter, ImageDraw

def cover_making(image_path, output_path, translated_text, logo_path='figure.png'):
    # 假设定义的全局变量，如果没有请在函数内定义
    # 推荐设置：小红书黄金比例 3:4
    TARGET_WIDTH = 1242
    TARGET_HEIGHT = 1660
    try:
        # 1. 处理背景图
        bg = Image.open(image_path).convert('RGBA')
        bg = bg.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
        
        # 2. 蒙层叠加
        overlay = Image.new('RGBA', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 60))
        canvas = Image.alpha_composite(bg, overlay)
        
        # 3. --- 新增：自适应缩放并嵌入 Logo ---
        if logo_path:
            logo = Image.open(logo_path).convert('RGBA')
            orig_w, orig_h = logo.size
            
            # 设定 Logo 占据背景宽度的比例 (例如 20%)
            logo_target_width = int(TARGET_WIDTH * 0.2)
            # 计算等比例缩放后的高度
            logo_target_height = int(orig_h * (logo_target_width / orig_w))
            
            # 执行 Resize
            logo = logo.resize((logo_target_width, logo_target_height), Image.Resampling.LANCZOS)
            
            # 设置边距 (Margin)
            margin = 40
            # 粘贴到左上角，(x, y) = (margin, margin)
            # 最后的 logo 参数作为 mask 必不可少，否则透明部分会黑框
            canvas.paste(logo, (margin, margin), logo)

        # 4. 保存结果
        # 注意：JPEG 不支持透明度，所以保存前转为 RGB
        canvas.convert('RGB').save(output_path, quality=95)
        print(f"✅ 成功生成带 Logo 封面: {output_path}")

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
你是一名B站国际时政与体育区的**金牌标题党（非虚假类）**。你的特长是将枯燥的外媒生肉，翻译成**中国年轻观众（Z世代）**一眼就能get到爽点、槽点或惊悚点的“高浓缩”标题。

# Input Data
- 原标题：{folder_name}
- 讨论主题：{topic_list}
- 字幕摘要：{srt_list}

# Core Philosophy (核心心法)
1. **去“新闻联播化”**：绝对不要写“某某人发表了关于某某的看法”。
2. **寻找“视觉钉子”**：标题里必须包含一个**可被视觉化**的动作、物品或具体数字。
   - ❌ 弱：特朗普指责拜登经济政策失败
   - ✅ 强：特朗普咆哮：拜登把牛奶价格搞到了10美元！
3. **建立“身份反差”**：如果人物身份有冲突，必须点出。
   - 示例：前任ICE局长 vs 现任被捕护士

# Construction Rules (强制执行)
1. **身份锚点（Identity Tag）**：
   - 必须使用中国观众熟悉的标签。
   - 规则：[知名度低的名字] + [强身份标签]。
   - 示例：Don Lemon -> 前CNN名嘴；Homan -> 边境沙皇。

2. **细节提取（Granularity）**：
   - 必须从字幕中提取最**毁三观、最打脸、或最具体**的一个细节（Quote/Action/Number）。
   - 严禁使用“痛斥”、“回应”、“表示”这种万能动词，请使用“回怼”、“嘲讽”、“泪崩”、“实锤”等带情绪动词。

3. **格式限制**：
   - **结构**：[核心冲突/情绪] + [具象化细节]
   - **长度**：20-40字。
   - **禁忌**：严禁使用半角符号 (: / \ ? * " < > |)，全部用空格或汉字代替。

# Few-Shot Examples (学习案例)
- Input: "Steph Curry talks about Butler's injury" (Content: Curry says he is heartbroken and Butler screamed in pain)
- Bad: 库里接受采访谈到了巴特勒的伤病情况
- Good: 勇士当家库里破防 亲眼目睹巴特勒韧带撕裂痛得惨叫

- Input: "Trump comments on Canada" (Content: Trump jokes Canada can't play hockey anymore)
- Bad: 特朗普表示加拿大和中国做生意很危险
- Good: 懂王特朗普杀人诛心 威胁加拿大再跟中国好就不准打冰球

# Workflow (思维链)
请先在内心思考：
1. 谁是主角？中国观众认识吗？不认识加什么前缀？
2. 视频里最劲爆的一个画面或一句话是什么？
3. 如何用“人话”把这两点串起来？

# Output Goal
输出一个文件名，不要包含任何前缀或后缀，直接输出结果。
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
        final_title = f"{clean_t}"
        titles.append(final_title)
        
        print(f" ✅ 生成标题: {final_title}")

    return titles, translated_texts

# ==================== 配置：文案与标签 (嘲讽/吃瓜风格) ====================

# 简介模板库（随机抽取，保持新鲜感，避免查重）
DESC_TEMPLATES = [
"【全球纵览】多维视角下的美式民主现状：冲突与重塑 本栏目系统梳理美媒内部争议实录，直击两党政治博弈的核心议题。我们主张跨越西方媒体的话语框架，通过一手素材还原真实的国际政治生态。 📢 声明：视频素材源自海外主流媒体，仅供批判性学术研究与语言进阶学习参考。 ✨ 订阅我们，每日获取深度资讯与逻辑解析。您的每一次认可对我们都至关重要。",
"⚡️ 深度洞察：美式政坛的话语体系解析与社会极化观察 精选美式政坛关键议题，不仅作为高阶双语学习素材，更旨在深度拆解西方社会叙事中的逻辑悖论。通过第一视角看懂权力博弈如何影响社会共识。 💡 观察点：聚焦政坛博弈，透析公共话语冲突背后的社会断裂面。 🤝 互动：坚持理性观察与独立思考。如果内容对您有启发，请点赞支持我们的深度内容创作。",
"🇺🇸 时代记录：当代美国政治生态的结构性演变实录 精选美媒犀利评论与政要辩论实况，通过精校双语字幕，确保精准传达政治修辞背后的深层含义。通过多维度的视角对比，为您拆解复杂的全球政治图景。 🎯 核心看点：选举局势动态 | 政策逻辑博弈 | 媒体语境透视 💬 交流：欢迎在评论区分享专业见解，共同探讨局势演变。感谢您的长期关注与支持。"
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

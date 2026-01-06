import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm
import yaml
import random
import os
import shutil
import requests
import json
import pandas as pd
from fuzzywuzzy import fuzz



# 常量定义
OUTPUT_DIR = 'output'
COVER_SUFFIX = '.jpg'
VIDEO_SUFFIX = '.mp4'
NEW_COVER_SUFFIX = '_new.png'
FONT_PATH = "Fonts\\msyhbd.ttc"  # 使用微软雅黑粗体
TAG = ['英语新闻, 英语学习, 川普, 马斯克, 咨询直通车, 社会观察局, 热点深度观察']
YAML_OUTPUT_FILE = 'config_bili.yaml'

error_dir = os.path.join(OUTPUT_DIR, 'ERROR')


# API 配置
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai'
#API_MODEL = 'LongCat-Flash-Chat'
#API_MODEL = 'gpt-4.1-nano'
API_MODEL = 'glm-4.7'


                        # 你是一位专业的新闻媒体专家，精通美国政治的人物，用词，典故，术语等。精通中英双语，熟悉新闻媒体的语言风格和表达规范。请将以下内容翻译成简体中文，并确保翻译结果符合以下要求：
                        # !确保使用中国网民观战容易理解听懂的言语；可基于主题内容小范围发挥，可以使用戏谑嘲讽等方式，使得标题更能增加点击率。涉及中国话题需站在中国立场，激发民族自豪感。例如 美国防长怂了，说中国威胁迫在眉睫；美国飞行员酸了,中国战机如此先进；

                        # 1. **准确性**：忠实于原文含义，避免歧义或误解，确保使用准确的标点符号！
                        # 2. **新闻风格**：使用正式、客观的语言，符合新闻媒体的表达习惯。
                        # 3. **流畅性**：语句通顺，逻辑清晰，易于读者理解。
                        # 4. **文化适应性**：确保翻译内容适合目标语言的文化背景，必要时进行本地化调整。
                        # 5. 语言风格： 严肃，专业，符合40岁以上男性喜好的风格，同时做到专业和有吸引力。
                        # 7. 基于内容中的频道名，确保准确的输出格式：仅输出一行内容，格式为：标题 ‖ 频道名。


                        # 注意事项：
                        # - 可额外补充一些内容（如时间、地点、人物等）
                        # - 如果原文中有专有名词（如人名、地名、机构名称），请确保翻译准确。
                        # - 如果原文中有口语化或非正式表达，请转换为新闻媒体常用的正式表达。
                        # - 如果原文中有文化特定的内容，请适当解释或替换为目标语言读者熟悉的概念。
#语言风格：整体保持新闻语体的庄重与客观，但标题可适度采用40岁以上男性受众偏好的硬朗、简练、略带讽刺张力的表达，避免低俗网络用语，杜绝戏谑过度。

#输出格式: 标题为主要涉及人物和主要情节
def translate_with_api(text, source_lang="en", target_lang="zh"):
    """
    使用自定义 API 进行翻译，并生成符合中文互联网习惯的标题。

    :param text: 需要翻译的文本
    :param source_lang: 源语言（默认：英文）
    :param target_lang: 目标语言（默认：中文）
    :return: 翻译后的文本
    """
    try:
        # 构建请求数据
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": API_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                
                    """
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
                                            )
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
        }

        # 发送 API 请求
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()  # 检查请求是否成功

        # 提取翻译结果
        translated_text = response.json()["choices"][0]["message"]["content"].strip()
        print(translated_text)
        return translated_text

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"解析响应失败: {e}")
        return None


# 检查 ERROR 文件夹是否存在
if os.path.exists(error_dir):
    # 删除 ERROR 文件夹及其所有子文件夹和文件
    shutil.rmtree(error_dir)
    print(f"已删除 {error_dir} 文件夹及其所有子文件夹和文件")
else:
    print(f"{error_dir} 文件夹不存在")


# COLOR_LIST = [
#     (255, 69, 0),    # 亮红色 (Bright Red)
#     (255, 140, 0),   # 深橙色 (Dark Orange)
#     (255, 215, 0),   # 金色 (Gold)
#     (0, 191, 255),   # 深天蓝色 (Deep Sky Blue)
# ]
COLOR_LIST = ["#FF1493", "#FF69B4", "#FFD700", "#FF6347", "#00BFFF", "#32CD32", "#FF4500", "#9370DB", "#FF8C00", "#1E90FF"]

def find_files_with_suffix(directory, suffix):
    """查找指定目录下具有特定后缀的文件"""
    return [os.path.join(root, file) for root, _, files in os.walk(directory) for file in files if file.endswith(suffix)]

def wrap_text(text, font, max_width):
    """将文本自动换行，确保每行不超过最大宽度（支持中文字符）"""
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

def draw_text_with_effects(draw, text, position, font, fill, outline_color=None, shadow_color=None, shadow_offset=(2, 2)):
    """
    绘制带轮廓和阴影的文字
    :param draw: ImageDraw 对象
    :param text: 文字内容
    :param position: 文字位置 (x, y)
    :param font: 字体对象
    :param fill: 文字颜色
    :param outline_color: 轮廓颜色（可选）
    :param shadow_color: 阴影颜色（可选）
    :param shadow_offset: 阴影偏移量 (dx, dy)
    """
    x, y = position
    dx, dy = shadow_offset

    # 绘制阴影
    if shadow_color:
        draw.text((x + dx, y + dy), text, font=font, fill=shadow_color)

    # 绘制轮廓
    if outline_color:
        for ox in [-1, 0, 1]:
            for oy in [-1, 0, 1]:
                if ox != 0 or oy != 0:  # 避免重复绘制正常文字
                    draw.text((x + ox, y + oy), text, font=font, fill=outline_color)

    # 绘制正常文字
    draw.text((x, y), text, font=font, fill=fill)
def create_gradient_overlay(width, height, start_alpha=150, end_alpha=225, gradient_height_percent=0.3):
    """
    创建渐变透明遮罩 - 在图片下方指定百分比区域创建渐变
    :param width: 图片宽度
    :param height: 图片高度
    :param start_alpha: 开始透明度（顶部）
    :param end_alpha: 结束透明度（底部）
    :param gradient_height_percent: 渐变区域占图片高度的百分比（默认30%）
    :return: 渐变遮罩图片
    """
    # 创建渐变遮罩
    gradient = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    
    # 计算渐变区域
    gradient_height = int(height * gradient_height_percent)  # 渐变区域高度
    gradient_start = height - gradient_height  # 渐变开始位置（从图片底部向上30%）
    
    # 绘制渐变效果
    for y in range(gradient_start, height):
        # 计算当前行在渐变中的位置比例 (0到1)
        progress = (y - gradient_start) / gradient_height
        
        # 计算当前行的透明度
        alpha = int(start_alpha + (end_alpha - start_alpha) * progress)
        
        # 绘制当前行
        draw.rectangle([(0, y), (width, y + 1)], fill=(0, 0, 0, alpha))
    
    return gradient

# def cover_making(image_path, output_path, translated_text):
#     """生成封面图片，并将翻译后的文字嵌入到封面中间偏下并靠左或靠右"""
#     try:
#         background = Image.open(image_path)
#         width, height = background.size
        
#         # 字体加载
#         font_date = ImageFont.truetype(FONT_PATH, 55)  # 字体放大
#         font_text = ImageFont.truetype(FONT_PATH, 90)  # 字体放大
        
#         draw = ImageDraw.Draw(background)
        

#         # 绘制日期
#         current_date = datetime.now().strftime("%Y-%m-%d")
#         date_bbox = draw.textbbox((0, 0), current_date, font=font_date)
#         date_position = (20, 50)  # 日期整体下移
#         draw_text_with_effects(
#             draw, current_date, date_position, font_date,
#             fill="yellow", outline_color="black", shadow_color="rgba(0, 0, 0, 128)"
#         )
        
#         # 绘制双语文本
#         text_cn_en = "中英双语"
#         text_cn_en_bbox = draw.textbbox((0, 0), text_cn_en, font=font_date)
#         text_cn_en_position = (width - 50 - text_cn_en_bbox[2], 50)  # 双语文本整体下移
#         draw_text_with_effects(
#             draw, text_cn_en, text_cn_en_position, font_date,
#             fill="white", outline_color="black", shadow_color="rgba(0, 0, 0, 128)"
#         )
        
#         # 随机选择一种颜色
#         text_color = random.choice(COLOR_LIST)

#         background.save(output_path)
#         print(f'Saving figure to {output_path}')
#     except IOError as e:
#         print(f"Error processing image {image_path}: {e}")
def cover_making(image_path, output_path, translated_text):
    """生成封面图片，并将翻译后的文字嵌入到封面中间偏下并靠左或靠右"""
    try:
        background = Image.open(image_path)
        width, height = background.size
        
        # 字体加载
        font_date = ImageFont.truetype(FONT_PATH, 55)  # 字体放大
        font_text = ImageFont.truetype(FONT_PATH, 200)  # 字体放大
        font_bilingual = ImageFont.truetype(FONT_PATH, 50)
        
        # 创建渐变遮罩（图片下30%区域）
        gradient_overlay = create_gradient_overlay(width, height, start_alpha=120, end_alpha=300, gradient_height_percent=0.45)
        
        # 将渐变遮罩应用到背景图片
        background = background.convert('RGBA')
        background = Image.alpha_composite(background, gradient_overlay)
        
        draw = ImageDraw.Draw(background)
        
        # 绘制日期（左上角）
        # current_date = datetime.now().strftime("%Y-%m-%d")
        # date_position = (30, 30)
        # draw_text_with_effects(
        #     draw, current_date, date_position, font_date,
        #     fill="white", outline_color="yellow", shadow_color="rgba(0, 0, 0, 128)"
        # )
        
        # 绘制双语文本（右上角）
        text_cn_en = "中英双语"
        text_cn_en_bbox = draw.textbbox((0, 0), text_cn_en, font=font_bilingual)
        text_cn_en_position = (width - 50 - text_cn_en_bbox[2], 30)
        draw_text_with_effects(
            draw, text_cn_en, text_cn_en_position, font_bilingual,
            fill="white", outline_color="white", shadow_color="rgba(0, 0, 0, 128)"
        )
        
        # 随机选择一种颜色
        text_color = random.choice(COLOR_LIST)
        
        # 添加文字绘制逻辑
        if translated_text:
            # 文本区域设置（确保在渐变区域内）
            text_area_width = width - 100  # 左右各留50px边距
            text_start_y = height * 0.50  # 从图片50%高度开始（确保在渐变区域内）
            
            # 动态调整字体大小以适应文本
            font_size = 150  # 起始字体大小
            while font_size > 65:  # 最小字体大小
                font_text_adjusted = ImageFont.truetype(FONT_PATH, font_size)
                lines = wrap_text(translated_text, font_text_adjusted, text_area_width)
                
                # 限制最大行数
                if len(lines) > 3:
                    lines = lines[:3]
                    if len(lines) == 3:
                        # 在第三行末尾添加省略号
                        last_line = lines[2]
                        while font_text_adjusted.getlength(last_line + "...") > text_area_width and len(last_line) > 0:
                            last_line = last_line[:-1]
                        lines[2] = last_line + "..."
                
                # 计算总文本高度
                line_height = font_text_adjusted.getbbox("测试")[3] + 15  # 行间距
                total_text_height = len(lines) * line_height
                
                # 检查是否超出可用空间
                available_height = height - text_start_y
                if total_text_height <= available_height * 0.8:  # 留20%空间
                    break
                    
                font_size -= 5  # 每次减小5px
            
            # 使用调整后的字体
            font_text = font_text_adjusted
            
            # 重新计算行高和总高度
            lines = wrap_text(translated_text, font_text, text_area_width)
            if len(lines) > 3:
                lines = lines[:3]
                if len(lines) == 3:
                    last_line = lines[2]
                    while font_text.getlength(last_line + "...") > text_area_width and len(last_line) > 0:
                        last_line = last_line[:-1]
                    lines[2] = last_line + "..."
            
            line_height = font_text.getbbox("测试")[3] + 15
            total_text_height = len(lines) * line_height
            
            # 调整起始Y坐标以保证文本在指定区域内
            start_y = text_start_y + (height - text_start_y - total_text_height) // 2
            
            # 绘制每行文本
            for i, line in enumerate(lines):
                line_bbox = draw.textbbox((0, 0), line, font=font_text)
                line_width = line_bbox[2] - line_bbox[0]
                
                # 水平居中
                x = (width - line_width) // 2
                y = start_y + i * line_height
                
                # 绘制文本
                draw_text_with_effects(
                    draw, line, (x, y), font_text,
                    fill=text_color, 
                    outline_color="black", 
                    shadow_color="rgba(0, 0, 0, 180)",
                    shadow_offset=(3, 3)
                )

        # 转换回RGB模式保存
        background = background.convert('RGB')
        background.save(output_path)
        print(f'Saving figure to {output_path}')
    except IOError as e:
        print(f"Error processing image {image_path}: {e}")

# 简化版本 - 如果你只需要基本功能
def simple_read_topic(file_path):
    """简化版本，只读取topic字段"""
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    topics = [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]
    return topics

def find_channel_by_fuzzy_match(file_path, target_title, min_similarity=80):
    """
    使用模糊匹配查找 Excel 中最接近的标题，返回对应的 channel_name
    
    参数:
        file_path (str): Excel 文件路径
        target_title (str): 要查找的标题（可以带符号，如 🚨）
        min_similarity (int): 最低相似度（0-100），默认 80
        
    返回:
        str: 匹配的 channel_name，如果没有足够相似的则返回 None
    """
    try:
        # 读取 Excel
        df = pd.read_excel(file_path)
        
        # 检查是否有必要的列
        if 'title' not in df.columns or 'channel_name' not in df.columns:
            print("⚠️ Excel 缺少 'title' 或 'channel_name' 列")
            return None
        
        best_match = None
        best_score = 0
        
        # 遍历每一行，计算相似度
        for index, row in df.iterrows():
            current_title = str(row['title'])  # 避免 NaN 报错
            similarity = fuzz.ratio(target_title.lower(), current_title.lower())
            
            # 如果相似度更高，则更新最佳匹配
            if similarity > best_score and similarity >= min_similarity:
                best_score = similarity
                best_match = row['channel_name']
                
        if best_match:
            print(f"✅ 最佳匹配（相似度 {best_score}%）：'{best_match}'")
            return best_match
        else:
            print(f"❌ 没有找到相似度 ≥{min_similarity}% 的标题")
            return None
            
    except Exception as e:
        print(f"❌ 发生错误：{e}")
        return None


def generate_titles(video_paths):
    """生成视频标题，基于视频所在文件夹的名称进行翻译，并保存翻译结果到新列表"""
    titles = []
    translated_texts = []  # 用于保存翻译结果的列表
    for video_path in video_paths:
        # 获取视频所在文件夹的名称
        folder_name = os.path.basename(os.path.dirname(video_path))
        json_name = os.path.join('output',folder_name,'gpt_log','summary.json')
        # 翻译文件夹名称
        topic = simple_read_topic(json_name)
        print(topic)


        excel = r'E:\Bilinew\VideoLingo-main\batch\tasks_setting.xlsx'
        channel_name = find_channel_by_fuzzy_match(excel,folder_name)
        print(channel_name)

        content = "频道名为：" + str(channel_name) + "标题为:" + str(folder_name) + '主题为:' + str(topic)

        #content = str(folder_name) + str(topic)
        translated = translate_with_api(content)

        #translate_with_api
        # 确保翻译结果不为空，如果翻译失败则使用原文件夹名称
        if not translated:
            translated = folder_name
        # 保存翻译结果
        translated_texts.append(translated)

        current_date = datetime.now()  # 获取当前日期和时间
        month_day = current_date.strftime("%m-%d")  # 格式化为 "月-日"

        # 1. YYYY-MM-DD 格式（如：2025-05-27）
        year_month_day = current_date.strftime("%Y-%m-%d")

        # 生成标题
        #full_title = f" {translated} | {month_day} "
        full_title = f"【熟肉】 {translated} | {month_day} "

        print(full_title)
        titles.append(full_title)
    return titles, translated_texts


import random

def generate_binary_sequence(length, percentage):
    # 计算1的数量
    num_ones = int(length * percentage / 100)
    # 生成包含指定数量1和0的列表
    sequence = [1] * num_ones + [0] * (length - num_ones)
    # 随机打乱顺序
    random.shuffle(sequence)
    return sequence


def create_yaml_config(videos, covers, titles, dtimes, yaml_file):
    print('recreating yaml')
    """创建YAML配置文件"""

    desc_text = (
        "本频道致力于分享中英双语的时事内容、热点解读与观点碰撞。\n"
        "我们希望用更平易近人的方式，一起了解世界，也能为英语学习提供真实有料的素材。\n"
        "内容仅供学习与交流，请勿过度解读，更不代表任何立场。观点多元，欢迎理性讨论！\n"
        "视频素材来自公开网络与授权资源，如有侵权请私信或留言联系删除。\n"
        "如果觉得频道还不错，拜托动动手：点赞、投币、收藏，顺手点个关注！\n"
        "更希望得到大家的【充电支持】，这是我们持续更新的最大动力！\n\n"
        "Eternal vigilance is the price of liberty"
    )

    data = {
        "submit": "app",
        "limit": 3,
        "streamers": {
            video: {
                "copyright": 1,
                "no_reprint": 1,
                "source": None,
                "tid": 208,
                "cover": cover,
                "title": title,
                "desc_format_id": 0,
                "topic_id": 1167972,
                "topic_detail": {
                    "from_topic_id": 1167972,
                    "from_source": "arc.web.recommend"
                },
                "desc": desc_text,
                "dolby": 1,
                "lossless_music": 1,
                "tag": TAG[0],
                "dynamic": "",
                #"dtime": dtime,
                "dtime": None,
                "open-elec" : 1,        #是否开启充电, 0-关闭 1-开启 [default: 0]

            #} for video, cover, title in zip(videos, covers, titles)
            } for video, cover, title, dtime in zip(videos, covers, titles, dtimes)

        }}
    
    try:
        with open(yaml_file, 'w', encoding='utf-8') as file:
            yaml.dump(data, file, allow_unicode=True, sort_keys=False)
        print(f"YAML 内容已成功保存到 {yaml_file}")
    except yaml.YAMLError as exc:
        print("YAML 格式化错误:", exc)
    except Exception as e:
        print("文件保存时出错:", e)

def create_yaml_config_charge(videos, covers, titles, dtimes, yaml_file):
    """保存指定视频列表为 付费 YAML"""

    desc_text = (
        "本频道致力于分享中英双语的时事内容、热点解读与观点碰撞。\n"
        "我们希望用更平易近人的方式，帮大家了解世界，也能为英语学习提供真实有料的素材。\n"
        "内容仅供学习与交流，请勿过度解读，更不代表任何立场。观点多元，欢迎理性讨论！\n"
        "视频素材来自公开网络与授权资源，如有侵权请私信或留言联系删除。\n"
        "如果觉得频道还不错，拜托动动手：点赞、投币、收藏，顺手点个关注！\n"
        "更希望得到大家的【充电支持】，这是我们持续更新的最大动力！\n\n"
        "Eternal vigilance is the price of liberty"
    )
    data = {
        "limit": 3,
        "submit": "app",
        "streamers": {
            video: {
                "copyright": 1,
                "no_reprint": 1,
                "source": None,
                "tid": 208,
                "cover": cover,
                "title": title,
                "topic_id": 1167972,
                "topic_detail": {
                    "from_topic_id": 1167972,
                    "from_source": "arc.web.recommend"
                },
                "desc_format_id": 0,
                "desc": desc_text,
                "dolby": 1,
                "lossless_music": 1,
                "tag": TAG[0],
                "dynamic": "",
                #"dtime": dtime,
                "dtime": None,
                "open-elec": 1,
                "charging_pay": 1,
                "preview": {
                    "need_preview": 1,
                    "start_time": 0,
                    "end_time": 2
                },
                "upower_level_id": "1212996740244948080",#1212996740244948080
                "upower_mode": 0,
                "upower_unit_price": 0,
            } for video, cover, title, dtime in zip(videos, covers, titles, dtimes)
        }
    }

    with open(yaml_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"付费 YAML 已保存：{yaml_file}")

def split_and_create_yaml(videos, covers, titles, dtimes):
    """80% 免费 + 20% 付费 分开生成"""
    total = len(videos)
    indices = list(range(total))
    random.shuffle(indices)

    split_point = int(total * 0.9)

    free_indices = indices[:split_point]
    paid_indices = indices[split_point:]

    # 免费内容
    free_videos = [videos[i] for i in free_indices]
    free_covers = [covers[i] for i in free_indices]
    free_titles = [titles[i] for i in free_indices]
    #free_dtimes = [dtimes[i] for i in free_indices]
    create_yaml_config(free_videos, free_covers, free_titles, dtimes, 'free_content.yaml')

    # 付费内容
    paid_videos = [videos[i] for i in paid_indices]
    paid_covers = [covers[i] for i in paid_indices]
    paid_titles = [titles[i] for i in paid_indices]
    #paid_dtimes = [dtimes[i] for i in paid_indices]
    create_yaml_config_charge(paid_videos, paid_covers, paid_titles, dtimes, 'paid_content.yaml')


# def timed_published(videos):

#     from datetime import datetime, timedelta

#     video_count =len(videos)

#     print(f"总视频个数: {video_count}")
    
#     # 2. 自定义函数：生成每天的三个发布时间（早7点、8点、9点）
#     def generate_publish_times(start_date, days):
#         """
#         生成每天的三个发布时间。
#         :param start_date: 开始日期（datetime对象）
#         :param days: 需要生成的天数
#         :return: 返回一个包含发布时间的列表
#         """
#         publish_times = []
#         for day in range(days):
#             current_date = start_date + timedelta(days=day)
#             # 生成当天的三个时间
#             publish_times.append(current_date.replace(hour=1, minute=0, second=0))  # 
#             publish_times.append(current_date.replace(hour=6, minute=30, second=0))  # 
#             publish_times.append(current_date.replace(hour=7, minute=0, second=0))  # 
#             publish_times.append(current_date.replace(hour=8, minute=30, second=0))  # 
#             publish_times.append(current_date.replace(hour=12, minute=00, second=0))  # 
#         return publish_times
    
#     # 3. 计算需要的天数
#     days_needed = (video_count // 3) + (1 if video_count % 3 != 0 else 0)
#     print(f"需要的天数: {days_needed}")
    
#     # 4. 设置起始日期（从今天开始）
#     start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
#     start_date = start_date + timedelta(days=1)

#     # 5. 生成发布时间
#     publish_times = generate_publish_times(start_date, days_needed)
    
#     dtimes = [int(time.timestamp()) for time in publish_times]

#     return dtimes
def timed_published(videos):
    from datetime import datetime, timedelta, timezone

    video_count = len(videos)
    print(f"总视频个数: {video_count}")
    
    def generate_publish_times(start_date, days):
        publish_times = []
        for day in range(days):
            current_date = start_date + timedelta(days=day)
            #publish_times.append(current_date.replace(hour=7, minute=30, second=0))
            publish_times.append(current_date.replace(hour=8, minute=0, second=0))
            publish_times.append(current_date.replace(hour=9, minute=30, second=0))
        return publish_times
    
    days_needed = (video_count // 3) + (1 if video_count % 3 != 0 else 0)
    print(f"需要的天数: {days_needed}")
    
    # 使用UTC+8时区
    utc8 = timezone(timedelta(hours=8))
    start_date = datetime.now(utc8).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    publish_times = generate_publish_times(start_date, days_needed)
    dtimes = [int(time.timestamp()) for time in publish_times]

    return dtimes[:video_count]


def find_output_with_sub_files(directory):
    """查找指定目录下所有子文件夹中名为 output_with_sub.mp4 的文件"""
    return [os.path.join(root, file) 
            for root, _, files in os.walk(directory) 
            for file in files 
           # if file == 'output_sub.mp4']
            if file == 'output_sub_final.mp4']

def main():
    # 查找封面和视频文件
    covers = find_files_with_suffix(OUTPUT_DIR, COVER_SUFFIX)
    videos = find_output_with_sub_files(OUTPUT_DIR)
    
    dtimes = timed_published(videos)

    #充电百分比：30%
    lens = len(videos) 
    lens = len(videos)
    percentage = 30  # 30%

    sequence = generate_binary_sequence(lens, percentage)
    print(sequence)

    # 生成标题和翻译结果
    titles, translated_texts = generate_titles(videos)
    
    # 生成新封面
    for cover, translated_text in tqdm(zip(covers, translated_texts), desc="Processing covers"):
        # 获取原始封面文件的目录
        cover_dir = os.path.dirname(cover)
        # 生成新封面文件名
        new_cover_name = os.path.basename(cover).split(COVER_SUFFIX)[0] + NEW_COVER_SUFFIX
        # 生成新封面的完整路径
        output_path = os.path.join(cover_dir, new_cover_name)

        translated_text_simple = translated_text.split('‖')[0]
        # 生成封面，并嵌入翻译后的文字
        cover_making(cover, output_path, translated_text_simple)
    
    # 查找新封面
    new_covers = find_files_with_suffix(OUTPUT_DIR, NEW_COVER_SUFFIX)
    
    print(len(new_covers))
    print(len(videos))
    print(len(titles))

    # 创建YAML配置文件
    #create_yaml_config(videos, new_covers, titles, dtimes)
   # create_yaml_config(videos, new_covers, titles)
    #create_yaml_config(videos, new_covers, titles, dtimes)
    split_and_create_yaml(videos, new_covers, titles, dtimes)
if __name__ == "__main__":
    main()

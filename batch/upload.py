import os
import yaml
import requests
from datetime import datetime, timedelta, timezone

# ==================== 常量配置（按需修改） ====================
OUTPUT_DIR = 'output'
VIDEO_SUFFIX = 'output_sub.mp4'  # 目标视频后缀
COVER_FORMATS = ['.png', '.jpg']       # 支持的封面格式
TAG = '英语新闻, 英语学习, 川普, 马斯克, 咨询直通车, 社会观察局, 热点深度观察'
YAML_OUTPUT_FILE = 'config_bili.yaml'

# API 配置
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai'
API_MODEL = 'gemini-2.5-flash-lite'

# ==================== 核心工具函数 ====================
def find_files_with_suffix(directory, suffix):
    """查找指定目录下所有带指定后缀的文件"""
    return [
        os.path.join(root, file)
        for root, _, files in os.walk(directory)
        for file in files if file.endswith(suffix)
    ]

def find_cover_for_folder(folder_path):
    """在指定文件夹内查找封面：文件夹名.png 或 文件夹名.jpg"""
    folder_name = os.path.basename(folder_path)
    for fmt in COVER_FORMATS:
        cover_path = os.path.join(folder_path, f"{folder_name}{fmt}")
        if os.path.exists(cover_path):
            return cover_path
    print(f"⚠️ 未在 {folder_path} 找到封面（{folder_name}.png/.jpg）")
    return ""

def translate_with_api(text):
    """调用 API 翻译文本并生成符合要求的标题"""
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
                    "content": """你是资深国际政治新闻编辑，精通中美双语。
                    基于输入文本生成20-35字中文标题，符合40岁以上男性喜好，风格硬朗简练，无额外字符、注释。"""
                },
                {"role": "user", "content": text}
            ]
        }
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()  # 捕获请求错误
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"⚠️ 翻译失败: {e} | 原文: {text}")
        return text  # 失败时返回原文

def generate_publish_times(video_count):
    """生成视频发布时间戳（UTC+8 时区，每天 8:00/9:30 两个时间点）"""
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
    """生成 B 站投稿 YAML 配置文件"""
    desc_text = """本频道分享中英双语时事内容，为英语学习提供真实素材。
内容仅供交流，不代表任何立场。感谢点赞、关注、充电支持！"""

    # 构造 YAML 数据结构
    data = {
        "submit": "app",
        "limit": 3,
        "streamers": {
            video: {
                "copyright": 1,
                "no_reprint": 1,
                "tid": 208,
                "cover": cover,  # 自动匹配的封面路径
                "title": title,
                "desc": desc_text,
                "tag": TAG,
                "dtime": dtime,
                "open-elec": 1
            } for video, cover, title, dtime in zip(videos, covers, titles, dtimes)
        }
    }

    # 写入 YAML 文件
    with open(yaml_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"\n✅ YAML 配置已生成: {yaml_file}")

# ==================== 主函数 ====================
def main():
    # 1. 查找目标视频文件
    videos = find_files_with_suffix(OUTPUT_DIR, VIDEO_SUFFIX)
    if not videos:
        print(f"❌ 未在 {OUTPUT_DIR} 目录下找到后缀为 {VIDEO_SUFFIX} 的视频文件")
        return
    print(f"✅ 共找到 {len(videos)} 个视频文件")

    # 2. 生成发布时间戳
    dtimes = generate_publish_times(len(videos))

    # 3. 翻译标题 + 自动匹配封面
    titles = []
    covers = []
    for video in videos:
        # 获取视频所在文件夹路径
        video_folder = os.path.dirname(video)
        # 获取文件夹名作为翻译素材
        folder_name = os.path.basename(video_folder)
        
        # 翻译生成标题
        translated_title = translate_with_api(folder_name)
        title = f"【熟肉】{translated_title} | {datetime.now().strftime('%m-%d')}"
        titles.append(title)

        # 自动查找封面
        cover = find_cover_for_folder(video_folder)
        covers.append(cover)

        print(f"📝 标题: {title}")
        print(f"🖼️  封面: {cover if cover else '未找到'}\n")

    # 4. 生成 YAML 配置文件
    create_yaml_config(videos, covers, titles, dtimes)

if __name__ == "__main__":
    main()

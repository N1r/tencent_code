import os
import shutil
import json
import time
import pandas as pd
from pathlib import Path
from datetime import datetime
from rapidfuzz import fuzz # 建议安装：pip install rapidfuzz
import requests
import re
# ==================== 配置区 ====================
# API 配置
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai'  # ✅ 修复尾部空格
#API_MODEL = 'sophnet/DeepSeek-V3.2'
#API_MODEL = 'gemini-2.5-flash-lite-preview-09-2025'
API_MODEL = 'qwen3-max-2026-01-23'

# ==================== 核心逻辑 ====================

# ==================== 文件处理 ====================
def simple_read_topic(file_path: str) -> list:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]

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


def sanitize_filename(filename):
    """清理文件名，确保符合系统规范且不含非法字符"""
    import re
    # 替换非法字符为下划线，包括冒号、引号、井号等
    filename = re.sub(r'[\\/:*?"<>|#\n\r\t]', '_', filename)
    return filename.strip()[:150] # 限制长度防止路径溢出

def get_unique_path(path: Path) -> Path:
    """处理同名文件，添加递增后缀"""
    counter = 1
    base, suffix = path.stem, path.suffix
    new_path = path
    while new_path.exists():
        new_path = path.parent / f"{base}_{counter}{suffix}"
        counter += 1
    return new_path

##仅输出一行文本，格式为：简短身份标签+人物名：核心冲击力观点 

# ==================== API 与翻译 ====================
def translate_with_api(text: str) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
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
   - 仅输出一行，严禁半角符号（: / \ ? * " < > |），字数35-50字。

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

from rapidfuzz import process, utils

def get_channel_info(file_path, target_name):
    """
    通过模糊匹配文件夹名，获取 Excel 中对应的频道名和描述
    """
    try:
        df = pd.read_excel(file_path)
        # 假设你的 Excel 列名分别是 'folder_keyword', 'channel_name', 'description'
        # 我们基于 'folder_keyword' 这一列来进行模糊匹配
        choices = df['title'].tolist()
        
        # 使用 rapidfuzz 进行模糊匹配，提取得分最高的一项
        match = process.extractOne(target_name, choices, processor=utils.default_process)
        
        if match and match[1] > 70:  # 设置 70 分为阈值，防止匹配太离谱
            matched_text = match[0]
            row = df[df['title'] == matched_text].iloc[0]
            
            return {
                "channel_name": row['channel_name'],
                "description": row['rawtext']
            }
    except Exception as e:
        print(f"读取 Excel 出错: {e}")
        
    return {"channel_name": "精选新闻", "description": "暂无描述"}

def process_and_move_files():
    """主程序：翻译 -> 重命名 -> 归档"""
    output_dir = Path("output").resolve()
    moved_files_dir = output_dir / "moved_files"
    moved_files_dir.mkdir(exist_ok=True)
    
    final_titles_for_noti = []
    
    # 获取待处理文件夹（排除 moved_files）
    folders = [f for f in output_dir.iterdir() if f.is_dir() and f.name != "moved_files" and not f.name.startswith('.')]
    
    for folder in folders:
        folder_name = folder.name
        print(f"\n--- 正在处理: {folder_name} ---")
        
        try:
            # 1. 获取翻译与标题生成
            # 尝试获取主题信息
            json_path = folder / 'gpt_log' / 'summary.json'
            topic_list = simple_read_topic(str(json_path)) if json_path.exists() else []
            
            srt_path = os.path.join(folder, 'trans.srt')
            srt_list = quick_read_srt(srt_path)
            #print(srt_list)

            # 模糊匹配频道名
            #channel_name = find_channel_by_fuzzy_match('tasks_setting.xlsx', folder_name) or "精选新闻"
            # --- 修改部分：获取频道名和描述 ---
            # 假设 find_channel_info 是你更新后的函数，返回 (频道名, 描述)
            channel_info = get_channel_info('tasks_setting.xlsx', folder_name)
            channel_name = channel_info.get('channel_name', "")
            channel_desc = channel_info.get('description', "")
            print(channel_desc)
            # API 生成标题党标题
            prompt_content = f"频道名为：{channel_name}\n原标题为:{folder_name}\n内容主题为:{topic_list}完整字幕: {srt_list}"

            #c#ontent = f"频道：{channel_name} 内容描述：{channel_desc} 原始名：{folder_name} 主题：{topic_list}"
            raw_translated_title = translate_with_api(prompt_content)
        
            if not raw_translated_title:
                print("  ⚠️ API 翻译失败，使用原始文件夹名")
                raw_translated_title = folder_name
            
            # 清理出安全的文件名
            safe_title = sanitize_filename(raw_translated_title)
            
            # 2. 归档核心文件
            # 目标: 视频(output_sub.mp4) 和 封面图(含_new的图片)
            
            # --- 新增：输出到 txt 文件 ---
            with open("最终结果.txt", "a", encoding="utf-8") as f:
                f.write(f"文件夹：{folder_name}\n")
                f.write(f"生成标题：{safe_title}\n")
                f.write("-" * 30 + "\n")
                
            target_files_found = False
            
            # 使用 os.scandir 避免之前的 FileNotFoundError 路径解析 Bug
            with os.scandir(str(folder)) as it:
                for entry in it:
                    if not entry.is_file():
                        continue
                    
                    file_path = Path(entry.path)
                    file_name = entry.name
                    dest_path = None

                    # 处理视频
                    if file_name == "output_sub.mp4":
                        dest_path = moved_files_dir / f"{safe_title}.mp4"
                    
                    # 处理图片 (带有 _new 的图片)
                    elif file_path.suffix.lower() in ['.jpg', '.jpeg', '.png'] and '_new' in file_path.stem:
                        dest_path = moved_files_dir / f"{safe_title}{file_path.suffix}"

                    if dest_path:
                        final_dest = get_unique_path(dest_path)
                        shutil.copy2(str(file_path), str(final_dest))
                        print(f"  ✅ 已归档: {file_name} -> {final_dest.name}")
                        target_files_found = True

            if target_files_found:
                final_titles_for_noti.append(raw_translated_title)
            
            # 适当留白避免 API 限制
            time.sleep(0.2)

        except Exception as e:
            print(f"  ❌ 处理文件夹 {folder_name} 出错: {e}")
            continue
if __name__ == "__main__":
    # 确保之前定义的函数（translate_with_api, find_channel_by_fuzzy_match 等）都在脚本中
    process_and_move_files()

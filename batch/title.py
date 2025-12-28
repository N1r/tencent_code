import os
import re
import logging
import requests
from pathlib import Path

# ===================== API 配置 =====================
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai/v1/chat/completions'
API_MODEL = 'gemini-2.5-flash-lite'
# ===================== 全局配置 =====================
ROOT_DIR = "./output"  # 标题文件夹所在根目录
LOG_FILE = "./subtitle_batch_summary.log"
OUTPUT_FILE = "./final_result.txt"  # 结果输出文件
# ===================== 日志配置 =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# ===================== 核心函数 =====================
def extract_subtitle_text(srt_path: str) -> str:
    """提取 SRT 纯文本，剔除序号、时间轴、空行"""
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"字幕文件不存在: {srt_path}")
    
    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    # 正则过滤无关行，合并连续文本
    pattern = r"^\d+$|^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$|^\s*$"
    lines = [line.strip() for line in content.split("\n") if not re.match(pattern, line.strip(), re.MULTILINE)]
    return " ".join(lines).strip()

def get_eye_catching_title(subtitle_text: str, folder_title: str) -> str:
    """调用模型生成 40+中年男性偏好的吸睛标题"""
    if not subtitle_text:
        return "【字幕文本为空】"
    
    # 适配 40+中年男性喜好的 Prompt
    prompt = f"""
任务：分析视频字幕+标题，生成**40+中年男性喜欢的吸睛视频标题**
核心偏好：
1.  偏爱「硬信息、有冲突、带干货、显格局」的内容，拒绝小鲜肉、无营养口水话
2.  喜欢直白犀利的表达，可带点江湖气、时政感、历史感，突出事件的「劲爆度」和「关键转折」
3.  优先从字幕中抓**爆点原句**，无原句则提炼核心事件，标题要短（15-30字）、有记忆点

要求：
1.  标题里必须包含关键人物/核心主体（从字幕或参考标题里找）
2.  不用严格套固定格式，怎么吸睛怎么来，但要一眼看出核心事件
3.  拒绝啰嗦，杜绝矫情，符合中年男性的信息获取习惯

视频参考标题：{folder_title}
字幕内容：
{subtitle_text}
"""
    
    payload = {
        "model": API_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.85,  # 提高随机性，增加标题张力
        "max_tokens": 70
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    try:
        response = requests.post(API_BASE_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        output = result["choices"][0]["message"]["content"].strip()
        return output
    except Exception as e:
        logging.error(f"API 调用失败: {str(e)}")
        return "【生成失败】"

def process_single_folder(folder_path: Path):
    """处理单个标题文件夹，返回生成的标题"""
    folder_title = folder_path.name
    srt_path = folder_path / "trans.srt"
    
    if not srt_path.exists():
        logging.warning(f"{folder_title} 缺少 trans.srt 文件，跳过")
        return None
    
    try:
        subtitle_text = extract_subtitle_text(str(srt_path))
        result_line = get_eye_catching_title(subtitle_text, folder_title)
        # 拼接 原文件夹名 + 生成标题，方便对照
        final_line = f"原标题参考：{folder_title} | 生成标题：{result_line}"
        logging.info(f"成功处理: {final_line}")
        return final_line
    except Exception as e:
        logging.error(f"处理 {folder_title} 失败: {str(e)}")
        return None

def batch_process():
    """批量处理所有标题文件夹，结果写入文件"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# 40+中年男性偏好 视频吸睛标题生成结果\n")
        f.write("# =========================================\n")
    
    root = Path(ROOT_DIR)
    folders = [f for f in root.iterdir() if f.is_dir()]
    
    if not folders:
        logging.warning("未找到任何标题文件夹")
        return
    
    logging.info(f"共发现 {len(folders)} 个待处理文件夹")
    
    for folder in folders:
        result_line = process_single_folder(folder)
        if result_line:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(f"{result_line}\n")
    
    logging.info(f"批量处理完成！结果已保存至 {OUTPUT_FILE}")

# ===================== 运行入口 =====================
if __name__ == "__main__":
    batch_process()
    print(f"\n✅ 所有任务执行完毕，结果文件: {OUTPUT_FILE}")

import os
import subprocess
import time
import sys
import platform
import cv2
import re
import numpy as np
from core._1_ytdlp import find_video_files
from core.utils import * # 假设 rprint 和 load_key 在这里

# ============= 1. 全局配置区域 =============

# 字体配置
FONT_NAME = 'Arial'
TRANS_FONT_NAME = 'HYWenHei' 

if platform.system() == 'Linux':
    FONT_NAME = 'Arial'
    TRANS_FONT_NAME = 'HYWenHei'
elif platform.system() == 'Darwin':
    FONT_NAME = 'Arial Unicode MS'
    TRANS_FONT_NAME = 'HYWenHei'

# 颜色定义
COLOR_WHITE = '&HFFFFFF'
COLOR_ORANGE = '&H0000A5FF' # 鲜艳橙色
COLOR_BLACK = '&H00000000'

# --- [模式 A: 横屏双语样式] ---
H_SRC_FONT_SIZE = 14
H_TRANS_FONT_SIZE = 24 
H_SRC_MARGIN_V = 20
H_TRANS_MARGIN_V = 65
H_WRAP_LIMIT = 20          

# --- [模式 B: 短视频竖屏单中文样式] ---
V_TRANS_FONT_SIZE = 12  
V_TRANS_MARGIN_V = 55     
V_TRANS_BACK_COLOR = '&H99000000' 
V_WRAP_LIMIT = 10           

# 文件路径
OUTPUT_DIR = "output"
OUTPUT_VIDEO = f"{OUTPUT_DIR}/output_sub.mp4"
SRC_SRT = f"{OUTPUT_DIR}/src.srt"
TRANS_SRT = f"{OUTPUT_DIR}/trans.srt"
WRAPPED_SRT = f"{OUTPUT_DIR}/trans_wrapped.srt"
LOGO_PATH = r"core/logo.png"

# ============= 2. 核心辅助逻辑 =============

def wrap_text_logic(text, limit):
    """手动硬换行逻辑"""
    text = text.replace('\n', ' ').strip()
    if len(text) <= limit:
        return text
    lines = [text[i:i + limit] for i in range(0, len(text), limit)]
    return "\\N".join(lines)

def process_srt_wrapping(input_srt, output_srt, limit):
    """预处理SRT文件进行换行"""
    if not os.path.exists(input_srt):
        return False
    with open(input_srt, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = re.compile(r'(\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n)(.*?)(?=\n\n|\n$|$)', re.DOTALL)
    def replace_func(match):
        return match.group(1) + wrap_text_logic(match.group(2), limit)
    
    new_content = pattern.sub(replace_func, content)
    with open(output_srt, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return True

def build_style(font_size, font_name, font_color, outline_color, outline_width, back_color, margin_v, margin_lr=30):
    """生成 ASS 样式字符串"""
    return (
        f"FontSize={font_size},FontName={font_name},"
        f"PrimaryColour={font_color},OutlineColour={outline_color},"
        f"OutlineWidth={outline_width},BackColour={back_color},"
        f"BorderStyle=4,Alignment=2,MarginV={margin_v},"
        f"Bold=1,Spacing=1.5,Shadow=0,MarginL={margin_lr},MarginR={margin_lr}"
    )

def check_gpu_available():
    try:
        result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True)
        return 'h264_nvenc' in result.stdout
    except:
        return False

# ============= 3. 主逻辑 =============

def merge_subtitles_to_video():
    # 1. 获取视频并分析比例
    video_file = find_video_files()
    if not video_file or not os.path.exists(video_file):
        rprint("[bold red]❌ 未找到输入视频文件。[/bold red]")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    cap = cv2.VideoCapture(video_file)
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    is_vertical = orig_h > orig_w
    
    # --- 强制分辨率设定 ---
    if is_vertical:
        target_w, target_h = 1080, 1920
        rprint(f"📱 竖屏模式: 强制输出 [bold cyan]1080x1920[/bold cyan]")
    else:
        target_w, target_h = 1920, 1080
        rprint(f"💻 横屏模式: 强制输出 [bold cyan]1920x1080[/bold cyan]")

    # 2. 字幕换行预处理
    wrap_limit = V_WRAP_LIMIT if is_vertical else H_WRAP_LIMIT
    process_srt_wrapping(TRANS_SRT, WRAPPED_SRT, wrap_limit)

    # 3. 滤镜链构建
    # [A] 缩放与补黑边逻辑：force_original_aspect_ratio=decrease 确保不拉伸，pad 居中补齐
    filter_chain = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
    )

    # [B] 样式应用 (基于 target_h 计算缩放，确保在 1080p/1920p 下字体大小恒定)
    if is_vertical:
        d_trans_size = int(V_TRANS_FONT_SIZE * (target_h / 1920.0))
        d_margin_v = int(V_TRANS_MARGIN_V * (target_h / 1920.0))
        trans_style = build_style(d_trans_size, TRANS_FONT_NAME, COLOR_ORANGE, COLOR_BLACK, 0, V_TRANS_BACK_COLOR, d_margin_v, margin_lr=40)
        
        filter_chain += f",subtitles={WRAPPED_SRT}:force_style='{trans_style}'"
    else:
        d_src_size = int(H_SRC_FONT_SIZE * (target_h / 1080.0))
        d_trans_size = int(H_TRANS_FONT_SIZE * (target_h / 1080.0))
        d_src_margin = int(H_SRC_MARGIN_V * (target_h / 1080.0))
        d_trans_margin = int(H_TRANS_MARGIN_V * (target_h / 1080.0))

        src_style = build_style(d_src_size, FONT_NAME, COLOR_WHITE, COLOR_BLACK, 2.5, '&H66000000', d_src_margin)
        trans_style = build_style(d_trans_size, TRANS_FONT_NAME, COLOR_ORANGE, COLOR_BLACK, 3.5, '&H80000000', d_trans_margin)
        
        filter_chain += f",subtitles={SRC_SRT}:force_style='{src_style}',subtitles={WRAPPED_SRT}:force_style='{trans_style}'"
        #filter_chain += f"subtitles={WRAPPED_SRT}:force_style='{trans_style}'"

    # [C] Logo 处理
    has_logo = os.path.exists(LOGO_PATH)
    if has_logo:
        logo_w = int(target_w * (0.18 if is_vertical else 0.12))
        # 这里的 [v_main] 是为了将前面的滤镜结果命名，方便 overlay 引用
        filter_complex = f"[0:v]{filter_chain}[v_main];[1:v]scale={logo_w}:-1[logo];[v_main][logo]overlay=W-w-25:25"
    else:
        filter_complex = f"[0:v]{filter_chain}"

    # 4. FFmpeg 命令构建
    ffmpeg_cmd = ['ffmpeg', '-y', '-i', video_file]
    if has_logo:
        ffmpeg_cmd.extend(['-i', LOGO_PATH])
    
    ffmpeg_cmd.extend(['-filter_complex', filter_complex])

    # GPU 加速处理
    #gpu_active = load_key("ffmpeg_gpu") if "load_key" in globals() else check_gpu_available()
    #if gpu_active:
    #    ffmpeg_cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '23'])
    #else:
    ffmpeg_cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23'])

    ffmpeg_cmd.extend([
        '-c:a', 'copy',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        OUTPUT_VIDEO
    ])

    # 5. 执行渲染
    rprint("🚀 正在渲染，请稍候...")
    start_time = time.time()
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        rprint(f"\n✅ 完成! 耗时: {time.time() - start_time:.2f}s")
        rprint(f"📁 输出分辨率: {target_w}x{target_h}")
        rprint(f"📁 文件位置: [bold green]{OUTPUT_VIDEO}[/bold green]")
    except subprocess.CalledProcessError as e:
        rprint(f"\n❌ 出错: {e}")

if __name__ == "__main__":
    merge_subtitles_to_video()

import os
import subprocess
import time
import sys
import platform
import cv2
import numpy as np
from core._1_ytdlp import find_video_files
from core.utils import * # 假设 rprint 和 load_key 在这里

# ============= 1. 全局配置区域 =============

# 字体配置
FONT_NAME = 'Arial'
TRANS_FONT_NAME = 'HYWenHei' 

if platform.system() == 'Linux':
    FONT_NAME = 'HYWenHei'
    TRANS_FONT_NAME = 'HYWenHei'
elif platform.system() == 'Darwin':
    FONT_NAME = 'Arial Unicode MS'
    TRANS_FONT_NAME = 'Arial Unicode MS'

# --- [模式 A: 标准横屏双语样式] ---
H_SRC_FONT_SIZE = 14
H_TRANS_FONT_SIZE = 22
H_SRC_MARGIN_V = 8
H_TRANS_MARGIN_V = 54

# --- [模式 B: 短视频竖屏单中文样式] ---
V_TRANS_FONT_SIZE = 32      # 你要求的尺寸 20-22
V_TRANS_MARGIN_V = 180       # 位置中下，避开 App 按钮
V_TRANS_BACK_COLOR = '&H99000000' # 深色半透明底 (BorderStyle=4)

# 颜色定义
COLOR_WHITE = '&HFFFFFF'
COLOR_ORANGE = '&H0000A5FF'
COLOR_BLACK = '&H00000000'

# 文件路径
OUTPUT_DIR = "output"
OUTPUT_VIDEO = f"{OUTPUT_DIR}/output_sub.mp4"
SRC_SRT = f"{OUTPUT_DIR}/src.srt"
TRANS_SRT = f"{OUTPUT_DIR}/trans.srt"
LOGO_PATH = r"core/logo.png"

# ============= 2. 辅助工具函数 =============

def check_gpu_available():
    try:
        result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True)
        return 'h264_nvenc' in result.stdout
    except:
        return False

def build_style(font_size, font_name, font_color, outline_color, outline_width, back_color, margin_v, border_style=1):
    """
    border_style: 1=描边+阴影, 4=深色背景块
    """
    return (
        f"FontSize={font_size},FontName={font_name},"
        f"PrimaryColour={font_color},OutlineColour={outline_color},"
        f"OutlineWidth={outline_width},BackColour={back_color},"
        f"BorderStyle={border_style},Alignment=2,MarginV={margin_v},"
        f"Bold=1,Spacing=1,Shadow=0,MarginL=30,MarginR=30"
    )

# ============= 3. 核心主逻辑 =============

def merge_subtitles_to_video():
    # 1. 获取输入视频
    video_file = find_video_files()
    if not video_file or not os.path.exists(video_file):
        rprint("[bold red]❌ 未找到输入视频文件。[/bold red]")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 2. 自动检测分辨率与比例
    cap = cv2.VideoCapture(video_file)
    if not cap.isOpened():
        rprint("❌ 无法读取视频元数据。")
        return
    
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    is_vertical = orig_h > orig_w
    rprint(f"🎬 检测到视频分辨率: [bold cyan]{orig_w}x{orig_h}[/bold cyan] ({'竖屏' if is_vertical else '横屏'})")

    # 3. 计算缩放因子与样式
    if is_vertical:
        # --- 短视频逻辑 ---
        scale = orig_h / 1920.0  # 以 1080x1920 为基准缩放
        d_trans_size = int(V_TRANS_FONT_SIZE * scale)
        d_margin_v = int(V_TRANS_MARGIN_V * scale)
        
        # 仅生成中文字幕样式 (使用 BorderStyle=4 深色底)

    # 使用你要求的 HYWenHei + 橙色 + BorderStyle=4
        trans_style = build_style(
            d_trans_size, TRANS_FONT_NAME, COLOR_ORANGE, 
            COLOR_BLACK, 0, V_TRANS_BACK_COLOR, d_margin_v, MarginL=40, MarginR=40, border_style=4
        )
        filter_complex = f"subtitles={TRANS_SRT}:force_style='{trans_style}'"
        rprint(f"📱 应用: [bold orange1]短视频橙色大字模式[/bold orange1] (Size: {d_trans_size})")
    else:
        # --- 横屏双语逻辑 ---
        scale = orig_h / 1080.0  # 以 1920x1080 为基准缩放
        d_src_size = int(H_SRC_FONT_SIZE * scale)
        d_trans_size = int(H_TRANS_FONT_SIZE * scale)
        d_src_margin = int(H_SRC_MARGIN_V * scale)
        d_trans_margin = int(H_TRANS_MARGIN_V * scale)

        src_style = build_style(d_src_size, FONT_NAME, COLOR_WHITE, COLOR_BLACK, 4, '&H66000000', d_src_margin)
        trans_style = build_style(d_trans_size, TRANS_FONT_NAME, COLOR_ORANGE, COLOR_BLACK, 4, '&H80000000', d_trans_margin)
        
        filter_complex = f"subtitles={SRC_SRT}:force_style='{src_style}',subtitles={TRANS_SRT}:force_style='{trans_style}'"
        rprint("💻 已应用 [bold]横屏双语样式[/bold]")

    # 4. Logo 处理
    has_logo = os.path.exists(LOGO_PATH)
    if has_logo:
        logo_w = int(orig_w * (0.2 if is_vertical else 0.12))
        filter_complex += f"[v_sub];[1:v]scale={logo_w}:-1[logo];[v_sub][logo]overlay=W-w-20:20"

    # 5. 构建 FFmpeg 命令
    ffmpeg_cmd = ['ffmpeg', '-y', '-i', video_file]
    if has_logo:
        ffmpeg_cmd.extend(['-i', LOGO_PATH])
    
    ffmpeg_cmd.extend(['-filter_complex', filter_complex])

    # GPU / CPU 编码判断
    gpu_active = load_key("ffmpeg_gpu") if "load_key" in globals() else check_gpu_available()
    if gpu_active:
        ffmpeg_cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '23'])
    else:
        ffmpeg_cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23'])

    ffmpeg_cmd.extend([
        '-c:a', 'copy',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        OUTPUT_VIDEO
    ])

    # 6. 执行任务
    rprint("🚀 正在渲染视频，请稍候...")
    start_time = time.time()
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        rprint(f"\n✅ 处理完成! 耗时: {time.time() - start_time:.2f}s")
        rprint(f"📁 输出路径: [bold green]{OUTPUT_VIDEO}[/bold green]")
    except subprocess.CalledProcessError as e:
        rprint(f"\n❌ FFmpeg 运行出错: {e}")

if __name__ == "__main__":
    merge_subtitles_to_video()
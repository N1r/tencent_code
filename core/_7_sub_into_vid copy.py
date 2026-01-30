import os
import subprocess
import time
import sys
import platform
import cv2
import numpy as np
from core._1_ytdlp import find_video_files
from core.utils import * # 假设 rprint 和 load_key 在这里

# ============= 1. 配置区域 =============

# 字体配置 - 推荐方案：Arial/思源黑体组合
FONT_NAME = 'Arial'
#TRANS_FONT_NAME = 'Source Han Sans SC' # 如果没有安装此字体，Linux下会自动回退
TRANS_FONT_NAME = 'HYWenHei' # 如果没有安装此字体，Linux下会自动回退

if platform.system() == 'Linux':
    FONT_NAME = 'HYWenHei'
    TRANS_FONT_NAME = 'HYWenHei'
elif platform.system() == 'Darwin':
    FONT_NAME = 'Arial Unicode MS'
    TRANS_FONT_NAME = 'Arial Unicode MS'

# 字幕位置调整
SRC_MARGIN_V = 8    # 原文位置
TRANS_MARGIN_V = 54   # 译文位置

# 原文字幕样式
SRC_FONT_SIZE = 14
SRC_FONT_COLOR = '&HFFFFFF'      # 白色文字
SRC_OUTLINE_COLOR = '&H000000'   # 黑色描边
SRC_OUTLINE_WIDTH = 2.0          # 描边宽度
SRC_SHADOW_COLOR = '&H80000000'  # 半透明黑色阴影
SRC_BACK_COLOR = '&H66000000'    # 深灰色背景

# # 译文字幕样式&H003366FF
TRANS_FONT_SIZE = 20
TRANS_FONT_COLOR = '&H0000A5FF'    
TRANS_OUTLINE_COLOR = '&H00000000' 
TRANS_OUTLINE_WIDTH = 3
TRANS_BACK_COLOR = '&H80000000'

# 文件路径配置
OUTPUT_DIR = "output"
OUTPUT_VIDEO = f"{OUTPUT_DIR}/output_sub.mp4"       # 字幕合成后的中间文件
FINAL_VIDEO = f"{OUTPUT_DIR}/output_sub_final.mp4"  # 拼接片头片尾后的最终文件
SRC_SRT = f"{OUTPUT_DIR}/src.srt"
TRANS_SRT = f"{OUTPUT_DIR}/trans.srt"

# Logo 和 片头片尾路径 (请确保这些文件存在，或者修改路径)
LOGO_PATH = r"core/logo.png"  # 建议使用相对路径，根据实际情况修改
OPEN_CLIP = "video/open.mp4"
END_CLIP = "video/end.mp4"

# ============= 2. 辅助函数 =============

def check_gpu_available():
    try:
        result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True)
        return 'h264_nvenc' in result.stdout
    except:
        return False



def build_subtitle_style(font_size, font_name, font_color, outline_color, outline_width, back_color, margin_v):
    """生成 ASS/SRT 样式字符串"""
    return (
        f"FontSize={font_size},FontName={font_name},"
        f"PrimaryColour={font_color},OutlineColour={outline_color},"
        f"OutlineWidth={outline_width},BackColour={back_color},"
        f"BorderStyle=4,Alignment=2,MarginV={margin_v},"
        f"Bold=0,Italic=0,Spacing=1,Shadow=0,MarginL=25,MarginR=25"
    )
def build_subtitle_style_src(font_size, font_name, font_color, outline_color, outline_width, back_color, margin_v):
    """生成 ASS/SRT 样式字符串"""
    return (
        f"FontSize={font_size},FontName={font_name},"
        f"PrimaryColour={font_color},OutlineColour={outline_color},"
        f"OutlineWidth={outline_width},BackColour={back_color},"
        f"BorderStyle=4,Alignment=2,MarginV={margin_v},"
        f"Shadow=0,MarginL=15,MarginR=15"
    )


def create_placeholder_video():
    """如果没有视频，生成黑屏占位符"""
    os.makedirs(os.path.dirname(OUTPUT_VIDEO), exist_ok=True)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, 1, (1920, 1080))
    out.write(frame)
    out.release()

# ============= 3. 主逻辑 =============

def merge_subtitles_to_video():
    video_file = find_video_files()
    os.makedirs(os.path.dirname(OUTPUT_VIDEO), exist_ok=True)
    
    # 1. 获取分辨率配置
    # RESOLUTION = load_key("resolution") if "load_key" in globals() else "1920x1080"
    # try:
    #     TARGET_WIDTH, TARGET_HEIGHT = RESOLUTION.split('x')
    # except ValueError:
    rprint("[bold yellow]Invalid resolution format. Using default: 1920x1080[/bold yellow]")
    TARGET_WIDTH, TARGET_HEIGHT = "1920", "1080"

    # 处理纯黑屏模式
    # #if RESOLUTION == '0x0':
    # rprint("[bold yellow]Warning: Creating a 0-second black video placeholder.[/bold yellow]")
    # create_placeholder_video()
    # #return

    # 检查字幕文件
    if not os.path.exists(SRC_SRT) or not os.path.exists(TRANS_SRT):
        rprint("❌ Subtitle files not found in the 'output' directory.")
        exit(1)

    # 2. 构建 FFmpeg 命令 (Logo + 字幕)
    
    # 构建样式字符串
    src_style = build_subtitle_style_src(
        SRC_FONT_SIZE, FONT_NAME, SRC_FONT_COLOR,
        SRC_OUTLINE_COLOR, SRC_OUTLINE_WIDTH, SRC_BACK_COLOR, SRC_MARGIN_V
    )
    trans_style = build_subtitle_style(
        TRANS_FONT_SIZE, TRANS_FONT_NAME, TRANS_FONT_COLOR,
        TRANS_OUTLINE_COLOR, TRANS_OUTLINE_WIDTH, TRANS_BACK_COLOR, TRANS_MARGIN_V
    )

    # 构建 Filter Complex
    # 逻辑：[0:v]缩放并填充 -> [v]; [1:v]缩放logo -> [logo]; [v][logo]叠加 -> [final]
    # 注意：如果不需要Logo，可以简化此逻辑。这里加上了文件存在性检查。
    
    has_logo = os.path.exists(LOGO_PATH)
    
    filter_complex = f"[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2"
    
    # 添加字幕
    filter_complex += f",subtitles={SRC_SRT}:force_style='FontName={FONT_NAME},{src_style}'"
    filter_complex += f",subtitles={TRANS_SRT}:force_style='FontName={TRANS_FONT_NAME},{trans_style}'"
    
    if has_logo:
        filter_complex += "[v_sub];[1:v]scale=300:-1[logo];[v_sub][logo]overlay=W-w-20:20" # 右上角
    
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', video_file
    ]

    if has_logo:
        ffmpeg_cmd.extend(['-i', LOGO_PATH])
    
    ffmpeg_cmd.extend([
        '-filter_complex', filter_complex,
        '-c:a', 'copy'
    ])

    # GPU 加速检测
    ffmpeg_gpu = load_key("ffmpeg_gpu") if "load_key" in globals() else check_gpu_available()
    if ffmpeg_gpu:
        rprint("[bold green]Will use GPU acceleration (h264_nvenc).[/bold green]")
        ffmpeg_cmd.extend(['-c:v', 'h264_nvenc'])
    else:
        rprint('using default')
        #ffmpeg_cmd.extend(['-c:v', 'libx264','-preset','fast'])
        ffmpeg_cmd.extend([
            # 线程控制
            '-threads', '2',
            
            # 视频编码（B站要求 + 低资源优化）
            '-c:v', 'libx264',
            '-profile:v', 'high',          # B站要求
            '-level', '4.0',                # B站要求
            '-preset', 'veryfast',          # 速度和质量平衡
            '-tune', 'zerolatency',         # 减少内存占用
            
            # 码率控制（适合2核2G）
            '-b:v', '3000k',
            '-maxrate', '3500k',
            '-bufsize', '3500k',
            
            # 像素格式（B站必须）
            '-pix_fmt', 'yuv420p',
            
            # 音频编码（B站推荐）
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '48000',
            '-ac', '2',
            
            # 优化和兼容性
            '-movflags', '+faststart',
            '-max_muxing_queue_size', '1024',
            
            ])
        
    ffmpeg_cmd.append(OUTPUT_VIDEO)

    rprint("🎬 Start merging subtitles (and logo) to video...")
    start_time = time.time()
    
    # 执行 FFmpeg
    process = subprocess.Popen(ffmpeg_cmd)
    try:
        process.wait()
        if process.returncode != 0:
            rprint("\n❌ FFmpeg execution error during subtitle burn.")
            return
        rprint(f"\n✅ Subtitle merge done! Time: {time.time() - start_time:.2f} s")
    except Exception as e:
        rprint(f"\n❌ Error: {e}")
        if process.poll() is None:
            process.kill()
        return

    '''
    # ============= 4. 拼接流程 (Step 2) =============
    
    # 检查是否需要拼接 (检查文件是否存在)
    clips_to_concat = []
    
    # 1. 片头
    #if os.path.exists(OPEN_CLIP):
    #    clips_to_concat.append(OPEN_CLIP)
    
    # 2. 正片 (刚刚生成的带字幕视频)
    if os.path.exists(OUTPUT_VIDEO):
        clips_to_concat.append(OUTPUT_VIDEO)
        
    # 3. 片尾
    if os.path.exists(END_CLIP):
        clips_to_concat.append(END_CLIP)
        
    if len(clips_to_concat) <= 1:
        rprint("[bold yellow]Skipping concatenation (only 1 or 0 videos found). Final result is output_sub.mp4[/bold yellow]")
        return

    rprint("🎬 Start concatenating (Open + Main + End)...")
    
    concat_list_path = os.path.join(OUTPUT_DIR, "concat_list.txt")
    temp_files = []
    
    try:
        # 统一转码所有视频片段，防止合并时参数不一致导致报错
        # 必须确保分辨率、帧率、SAR、像素格式完全一致
        for i, input_file in enumerate(clips_to_concat):
            temp_file = os.path.join(OUTPUT_DIR, f"temp_concat_{i}.mp4")
            temp_files.append(temp_file)
            
            # 转码命令
            norm_cmd = [
                "ffmpeg", "-y",
                "-i", input_file,
                "-c:v", "h264_nvenc" if ffmpeg_gpu else "libx264",
                "-crf", "22", 
                "-pix_fmt", "yuv420p",
                "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT},setsar=1:1",
                "-r", "30", "-g", "60", # 强制30帧
                "-c:a", "aac", "-b:a", "128k",
                temp_file
            ]
            
            # 隐藏详细输出，只显示进度条或静默
            subprocess.run(norm_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            rprint(f"  Processed segment {i+1}/{len(clips_to_concat)}")

        # 写入 concat 列表
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for tf in temp_files:
                f.write(f"file '{os.path.abspath(tf)}'\n")

        # 执行拼接
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy", # 直接流拷贝，极快
            FINAL_VIDEO
        ]
        
        subprocess.run(concat_cmd, check=True)
        rprint(f"\n✅ All Done! Final video: [bold green]{FINAL_VIDEO}[/bold green]")

    except subprocess.CalledProcessError as e:
        rprint(f"\n❌ Concatenation failed: {e}")
    finally:
        # 清理临时文件
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)
        for tf in temp_files:
            if os.path.exists(tf):
                os.remove(tf)
'''

if __name__ == "__main__":
    merge_subtitles_to_video()

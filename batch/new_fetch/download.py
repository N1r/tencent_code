import pandas as pd
import yt_dlp
import os

# ============= 配置 =============
INPUT_CSV = 'bsky_tasks.csv'      # fetch 步骤生成的文件
DOWNLOAD_DIR = 'BlueSky_Downloads' # 下载保存目录

def download_from_csv():
    # 1. 检查文件
    if not os.path.exists(INPUT_CSV):
        print(f"❌ 未找到 {INPUT_CSV}，请先运行 fetch_bsky.py")
        return

    # 2. 读取任务
    try:
        df = pd.read_csv(INPUT_CSV)
        print(f"📂 读取到 {len(df)} 条任务")
    except Exception as e:
        print(f"❌ 读取 CSV 失败: {e}")
        return

    if 'Post URL' not in df.columns:
        print("❌ CSV 格式错误: 缺少 'Post URL' 列")
        return

    # 提取链接列表
    urls = df['Post URL'].tolist()

    # 3. 配置 yt-dlp
    ydl_opts = {
        # 文件命名格式: 目录/用户名/日期_ID_标题.mp4
        'outtmpl': f'{DOWNLOAD_DIR}/%(uploader)s/%(upload_date)s_%(id)s_%(title).30s.%(ext)s',
        
        # 格式选择
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        
        # 忽略错误，继续下载下一个
        'ignoreerrors': True,
        'no_warnings': True,
        
        # 并发分片下载，提升速度
        'concurrent_fragment_downloads': 4,
    }

    print("-" * 50)
    print(f"🚀 开始下载 {len(urls)} 个视频...")
    print(f"📂 保存位置: ./{DOWNLOAD_DIR}")
    print("-" * 50)

    # 4. 执行下载
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(urls)

    print("\n✅ 所有任务处理完毕！")

if __name__ == "__main__":
    download_from_csv()
import requests
import pandas as pd
import os
import logging
from tqdm import tqdm

# ============= 1. 配置区域 =============

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG = {
    # 目标 Bluesky 账号
    'TARGETS': [
        "acyn.bsky.social",
        "atrupar.com",
        "ronfilipkowski.bsky.social",
        "patriottakes.bsky.social",
        "meidastouch.bsky.social",
        "kamalahq.bsky.social",
        "waltermasterson.bsky.social",
        "thegoodliars.bsky.social",
    ],

    'CHECK_LIMIT': 10,  # 每个账号检查最近 50 条
    'OUTPUT_FILE': 'tasks_setting.xlsx'  # 目标 Excel 文件名
}

# 表头结构（严格对应截图）
COLUMNS = [
    'Video File', 
    'title', 
    'description', 
    'viewCount', 
    'channel_name', 
    'duration', 
    'Source Language', 
    'Target Language', 
    'Dubbing', 
    'Status'
]

# ============= 2. Bluesky 抓取逻辑 =============

class BlueskyFetcher:
    def __init__(self):
        self.api_root = "https://public.api.bsky.app/xrpc"

    def resolve_handle(self, handle):
        """解析用户名"""
        try:
            url = f"{self.api_root}/com.atproto.identity.resolveHandle"
            res = requests.get(url, params={"handle": handle}, timeout=10)
            if res.status_code == 200:
                return res.json().get("did")
        except:
            return None
        return None

    def get_latest_videos(self, handle, limit=50):
        """获取视频并格式化为目标结构"""
        did = self.resolve_handle(handle)
        if not did:
            return []

        url = f"{self.api_root}/app.bsky.feed.getAuthorFeed"
        params = {
            "actor": did,
            "limit": limit,
            "filter": "posts_with_video" 
        }

        try:
            res = requests.get(url, params=params, timeout=15)
            data = res.json()
            if "feed" not in data:
                return []
            
            rows = []
            for item in data["feed"]:
                post = item.get("post", {})
                record = post.get("record", {})
                
                # 1. 生成链接 (Video File)
                uri = post.get("uri", "")
                if not uri: continue
                post_id = uri.split("/")[-1]
                video_link = f"https://bsky.app/profile/{handle}/post/{post_id}"
                
                # 2. 处理文本 (Title / Description)
                raw_text = record.get("text", "")
                clean_title = raw_text.replace("\n", " ").strip()[:60] # 标题取前60字
                if not clean_title:
                    clean_title = f"Bluesky_Video_{post_id}"
                
                # 3. 获取点赞数作为 viewCount 的替代 (Bluesky无播放量)
                like_count = post.get("likeCount", 0)

                # 4. 构造符合 tasks_setting.xlsx 的行数据
                row = {
                    'Video File': video_link,
                    'title': clean_title,
                    'description': raw_text,
                    'viewCount': like_count,      # 用点赞数填充
                    'channel_name': handle,       # 频道名
                    'duration': 0,                # API无法获取时长，填0
                    'Source Language': 'en',
                    'Target Language': '简体中文',
                    'Dubbing': 0,
                    'Status': ''                  # 留空
                }
                rows.append(row)
            
            return rows
            
        except Exception as e:
            logger.error(f"Error fetching {handle}: {e}")
            return []

# ============= 3. 合并与保存逻辑 (Excel) =============

def merge_and_save_excel(new_data):
    filename = CONFIG['OUTPUT_FILE']
    
    if not new_data:
        print("⚠️ 本次未抓取到数据。")
        return

    # 转为 DataFrame
    new_df = pd.DataFrame(new_data)
    
    # 确保列顺序正确
    for col in COLUMNS:
        if col not in new_df.columns:
            new_df[col] = "" # 补全缺失列
    new_df = new_df[COLUMNS] # 重排顺序

    if os.path.exists(filename):
        try:
            # 读取旧 Excel
            old_df = pd.read_excel(filename)
            original_len = len(old_df)
            
            # 合并
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
            
            # 去重：根据 'Video File' 列判断
            # keep='first' 保留旧的记录（这样 Status 状态不会被覆盖）
            final_df = combined_df.drop_duplicates(subset=['Video File'], keep='first')
            
            added_count = len(final_df) - original_len
            print(f"🔄 更新完成：库中原有 {original_len} 条，新增 {added_count} 条。")
            
        except Exception as e:
            print(f"⚠️ 读取旧 Excel 失败 ({e})，将创建新文件。")
            final_df = new_df
            print(f"🆕 创建新任务文件，共 {len(final_df)} 条。")
    else:
        final_df = new_df
        print(f"🆕 创建新任务文件，共 {len(final_df)} 条。")

    # 保存为 Excel
    try:
        final_df.to_excel(filename, index=False)
        print(f"✅ 文件已保存至: {filename}")
    except PermissionError:
        print(f"❌ 保存失败！请先关闭 {filename} 文件再运行脚本！")

# ============= 4. 主程序 =============

def main():
    fetcher = BlueskyFetcher()
    all_videos = []
    
    print(f"🚀 开始扫描 Bluesky -> {CONFIG['OUTPUT_FILE']}")
    
    with tqdm(total=len(CONFIG['TARGETS'])) as pbar:
        for user in CONFIG['TARGETS']:
            pbar.set_description(f"扫描 {user}")
            videos = fetcher.get_latest_videos(user, limit=CONFIG['CHECK_LIMIT'])
            all_videos.extend(videos)
            pbar.update(1)

    print("-" * 50)
    merge_and_save_excel(all_videos)
    print("-" * 50)

if __name__ == "__main__":
    main()
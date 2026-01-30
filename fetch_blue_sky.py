import requests
import pandas as pd
import os
import logging
import time
import random
from tqdm import tqdm
from googletrans import Translator

# ============= 1. 配置区域 =============

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG = {
    'TARGETS': [
        "acyn.bsky.social",
        "atrupar.com",
        "thedailyshow.com",
        "briantylercohen.bsky.social",
        "thebulwark.com",
        "anthonyvslater.bsky.social",
        "latenightercom.bsky.social",
        "cwebbonline.com",
        "reuters.com",        
    ],
    'CHECK_LIMIT': 10, 
    'OUTPUT_FILE': 'batch/tasks_setting.xlsx',
    'ENABLE_TRANSLATION': False,  # 是否开启翻译功能
    'TARGET_LANG': 'zh-cn'       # 翻译目标语言
}

# 最终保存的列结构
COLUMNS = [
    'Video File', 
    'title', 
    'rawtext',
    'translated_text', # 新增翻译结果列
    'Publish Date',    
    'Replies',         
    'Reposts',         
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
        try:
            url = f"{self.api_root}/com.atproto.identity.resolveHandle"
            res = requests.get(url, params={"handle": handle}, timeout=10)
            if res.status_code == 200:
                return res.json().get("did")
        except:
            return None
        return None

    def get_latest_videos(self, handle, limit=50):
        did = self.resolve_handle(handle)
        if not did: return []

        url = f"{self.api_root}/app.bsky.feed.getAuthorFeed"
        params = {"actor": did, "limit": limit, "filter": "posts_with_video"}

        try:
            res = requests.get(url, params=params, timeout=15)
            data = res.json()
            if "feed" not in data: return []
            
            rows = []
            for item in data["feed"]:
                post = item.get("post", {})
                record = post.get("record", {})
                embed = post.get("embed", {})
                
                uri = post.get("uri", "")
                if not uri: continue
                post_id = uri.split("/")[-1]
                video_link = f"https://bsky.app/profile/{handle}/post/{post_id}"
                
                raw_text = record.get("text", "")
                clean_title = raw_text.replace("\n", " ").strip()[:50]
                
                raw_date = post.get("indexedAt", "")
                publish_date = raw_date.replace("T", " ").split(".")[0] if raw_date else ""
                
                # 尝试获取视频时长 (duration)
                v_duration = 0
                if embed.get('$type') == 'app.bsky.embed.video#view':
                    v_duration = embed.get('video', {}).get('duration', 0)

                rows.append({
                    'Video File': video_link,
                    'title': clean_title if clean_title else f"Video_{post_id}",
                    'rawtext': raw_text,
                    #'translated_text': "", # 初始为空，待后续翻译
                    'Publish Date': publish_date,
                    'Replies': post.get("replyCount", 0),
                    'Reposts': post.get("repostCount", 0),
                    'viewCount': post.get("likeCount", 0),
                    'channel_name': handle,
                    'duration': v_duration,
                    'Source Language': 'en',
                    'Target Language': '简体中文',
                    'Dubbing': 0,
                    'Status': ''
                })
            return rows
        except Exception as e:
            logger.error(f"Error fetching {handle}: {e}")
            return []

# ============= 3. 翻译逻辑 =============

def perform_translation(df):
    """对 DataFrame 中未翻译的 rawtext 进行翻译"""
    translator = Translator()
    # 筛选：rawtext 有内容 且 translated_text 为空的行
    mask = df['rawtext'].notna() & (df['translated_text'].astype(str).str.strip() == "")
    to_translate = df[mask]

    if to_translate.empty:
        return df

    print(f"🌐 正在翻译 {len(to_translate)} 条新内容...")
    for idx in tqdm(to_translate.index, desc="翻译进度"):
        try:
            text = str(df.at[idx, 'rawtext']).strip()
            if text:
                result = translator.translate(text, dest=CONFIG['TARGET_LANG'])
                df.at[idx, 'translated_text'] = result.text
                time.sleep(random.uniform(0.3, 0.8)) # 随机延时防封
        except Exception as e:
            logger.warning(f"翻译失败 (行 {idx}): {e}")
            continue
    return df

# ============= 4. 合并与保存 =============

def merge_and_save_excel(new_data):
    filename = CONFIG['OUTPUT_FILE']
    if not new_data:
        print("⚠️ 未发现新视频。")
        return

    new_df = pd.DataFrame(new_data)
    for col in COLUMNS:
        if col not in new_df.columns: new_df[col] = ""

    if os.path.exists(filename):
        try:
            old_df = pd.read_excel(filename)
            # 合并并根据链接去重，保留旧记录（保留已有的翻译和状态）
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
            final_df = combined_df.drop_duplicates(subset=['Video File'], keep='first')
        except:
            final_df = new_df
    else:
        final_df = new_df

    # 触发翻译功能
    if CONFIG['ENABLE_TRANSLATION']:
        final_df = perform_translation(final_df)

    # 排序：按发布时间倒序
    final_df = final_df.sort_values(by='viewCount', ascending=False)
    final_df = final_df[COLUMNS]

    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        final_df.to_excel(filename, index=False)
        print(f"✅ 处理完成！文件保存至: {filename}")
    except PermissionError:
        print(f"❌ 错误：请先关闭 Excel 文件 {filename}")

# ============= 5. 主程序 =============

def main():
    fetcher = BlueskyFetcher()
    all_videos = []
    print(f"🚀 开始任务: 扫描 -> 翻译 -> 导出")
    
    for user in CONFIG['TARGETS']:
        videos = fetcher.get_latest_videos(user, limit=CONFIG['CHECK_LIMIT'])
        all_videos.extend(videos)

    merge_and_save_excel(all_videos)

if __name__ == "__main__":
    main()
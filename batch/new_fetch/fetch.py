import requests
import pandas as pd
import os
import logging
from datetime import datetime
from tqdm import tqdm

# ============= 1. 配置区域 =============

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG = {
    # 目标账号列表
    'TARGETS': [
        "acyn.bsky.social",
        "atrupar.bsky.social",
        "ronfilipkowski.bsky.social",
        "patriottakes.bsky.social",
        "meidastouch.bsky.social",
        "kamalahq.bsky.social",
        "waltermasterson.bsky.social",
        "thegoodliars.bsky.social",
    ],

    # 每个账号检查最近多少条？
    'CHECK_LIMIT': 50,
    
    # 结果保存文件名
    'OUTPUT_FILE': 'bsky_tasks.csv'
}

# ============= 2. Bluesky 工具类 =============

class BlueskyFetcher:
    def __init__(self):
        self.api_root = "https://public.api.bsky.app/xrpc"

    def resolve_handle(self, handle):
        """将用户名转为 DID"""
        try:
            url = f"{self.api_root}/com.atproto.identity.resolveHandle"
            res = requests.get(url, params={"handle": handle}, timeout=10)
            if res.status_code == 200:
                return res.json().get("did")
        except Exception as e:
            logger.error(f"解析用户 {handle} 失败: {e}")
        return None

    def get_latest_videos(self, handle, limit=50):
        """获取用户的时间线视频"""
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
            
            videos = []
            for item in data["feed"]:
                post = item.get("post", {})
                record = post.get("record", {})
                
                uri = post.get("uri", "")
                if not uri: continue
                post_id = uri.split("/")[-1]
                post_url = f"https://bsky.app/profile/{handle}/post/{post_id}"
                
                # 提取完整文字
                raw_text = record.get("text", "")
                
                # 提取简短标题 (去换行)
                clean_title = raw_text.replace("\n", " ").strip()[:50]
                if not clean_title:
                    clean_title = f"Video_{post_id}"
                
                created_at = record.get("createdAt", "")
                
                videos.append({
                    "Handle": handle,
                    "Date": created_at[:10],
                    "Title": clean_title,
                    "Full Text": raw_text, # 保留完整文字
                    "Post URL": post_url,  # 去重唯一标识
                    "Post ID": post_id
                })
            
            return videos
            
        except Exception as e:
            logger.error(f"抓取 {handle} 失败: {e}")
            return []

# ============= 3. 核心：合并与去重逻辑 =============

def merge_and_save(new_data_list):
    """
    将新抓取的数据与 CSV 中的旧数据合并并去重
    """
    filename = CONFIG['OUTPUT_FILE']
    
    # 1. 将新数据转为 DataFrame
    new_df = pd.DataFrame(new_data_list)
    
    if new_df.empty:
        print("⚠️ 本次未抓取到任何数据。")
        return

    # 2. 检查是否存在旧文件
    if os.path.exists(filename):
        try:
            old_df = pd.read_csv(filename)
            original_count = len(old_df)
            
            # 合并旧数据和新数据
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
            
            # 3. 去重 (核心步骤)
            # subset=['Post URL']: 根据链接判断是否重复
            # keep='first': 保留第一次出现的(旧的)，这样不会打乱原有顺序，也可以选 'last'
            final_df = combined_df.drop_duplicates(subset=['Post URL'], keep='first')
            
            new_added_count = len(final_df) - original_count
            
            if new_added_count > 0:
                print(f"🔄 合并完成：库中原有 {original_count} 条，本次新增 {new_added_count} 条。")
            else:
                print(f"💤 没有发现新视频 (库中已有 {original_count} 条)。")
                
        except Exception as e:
            print(f"⚠️ 读取旧文件出错 ({e})，将直接覆盖保存。")
            final_df = new_df
            new_added_count = len(final_df)
    else:
        # 如果文件不存在，直接保存
        final_df = new_df
        new_added_count = len(final_df)
        print(f"🆕 创建新文件，共 {new_added_count} 条。")

    # 4. 排序 (按日期降序，让最新的在最上面)
    if 'Date' in final_df.columns:
        final_df = final_df.sort_values(by="Date", ascending=False)

    # 5. 保存
    final_df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"✅ 已保存至: {filename}")

# ============= 4. 主程序 =============

def main():
    fetcher = BlueskyFetcher()
    current_batch_videos = []
    
    print(f"🚀 开始扫描 Bluesky, 目标账号: {len(CONFIG['TARGETS'])} 个")
    
    with tqdm(total=len(CONFIG['TARGETS'])) as pbar:
        for user in CONFIG['TARGETS']:
            pbar.set_description(f"扫描 {user}")
            videos = fetcher.get_latest_videos(user, limit=CONFIG['CHECK_LIMIT'])
            current_batch_videos.extend(videos)
            pbar.update(1)

    print("\n" + "-"*50)
    # 调用合并去重函数
    merge_and_save(current_batch_videos)
    print("-"*50)

if __name__ == "__main__":
    main()
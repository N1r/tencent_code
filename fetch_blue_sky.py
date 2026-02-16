import requests
import pandas as pd
import os
import logging
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from colorama import init, Fore, Style
from tabulate import tabulate

# ============= 0. 初始化 =============
init(autoreset=True) # 初始化颜色

#AIzaSyDMVvDeq4xHWFpTh5hGRiZoBettBqrSbcs 
# 日志配置
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# ============= 1. 配置区域 =============

CONFIG = {
    'TARGETS': [
        "acyn.bsky.social",
        "atrupar.com",
        "thedailyshow.com",
        "briantylercohen.bsky.social",
        "thebulwark.com",
        #"anthonyvslater.bsky.social",
        "latenightercom.bsky.social",
        #"cwebbonline.com",
        #"reuters.com",        
    ],
    'CHECK_LIMIT': 20,           # 每个账号只检查最新的 X 条
    'OUTPUT_FILE': 'batch/tasks_setting.xlsx',
    'REQUEST_TIMEOUT': 10,
    'MAX_RETRIES': 3
}

# Excel 列结构 (保留 translated_text 列供手动填写，但不自动填充)
COLUMNS = [
    'Video File', 'title', 'rawtext', 'translated_text', 
    'Publish Date', 'Replies', 'Reposts', 'viewCount', 
    'channel_name', 'duration', 'Source Language', 
    'Target Language', 'Dubbing', 'Status'
]

# ============= 2. 工具类：打印助手 =============

class Printer:
    """负责美观的控制台输出"""
    @staticmethod
    def info(msg):
        print(f"{Fore.CYAN}ℹ️  {msg}{Style.RESET_ALL}")

    @staticmethod
    def success(msg):
        print(f"{Fore.GREEN}✅ {msg}{Style.RESET_ALL}")

    @staticmethod
    def warn(msg):
        print(f"{Fore.YELLOW}⚠️  {msg}{Style.RESET_ALL}")

    @staticmethod
    def error(msg):
        print(f"{Fore.RED}❌ {msg}{Style.RESET_ALL}")

    @staticmethod
    def header(msg):
        print(f"\n{Fore.MAGENTA}{'='*50}\n   {msg}\n{'='*50}{Style.RESET_ALL}")

# ============= 3. 核心抓取逻辑 (单次请求) =============

class BlueskyFetcher:
    def __init__(self):
        self.api_root = "https://public.api.bsky.app/xrpc"
        self.session = requests.Session()
        # 配置重试策略
        retries = Retry(total=CONFIG['MAX_RETRIES'], backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _get_request(self, endpoint, params=None):
        try:
            url = f"{self.api_root}/{endpoint}"
            res = self.session.get(url, params=params, timeout=CONFIG['REQUEST_TIMEOUT'])
            res.raise_for_status()
            return res.json()
        except Exception:
            return None 

    def resolve_handle(self, handle):
        data = self._get_request("com.atproto.identity.resolveHandle", {"handle": handle})
        if data and "did" in data:
            return data["did"]
        return None

    def get_latest_videos(self, handle, limit=20):
        """获取指定用户的最新视频帖子"""
        did = self.resolve_handle(handle)
        if not did:
            Printer.error(f"无法解析用户: {handle} (跳过)")
            return []

        params = {
            "actor": did, 
            "limit": limit, 
            "filter": "posts_with_video" 
        }

        data = self._get_request("app.bsky.feed.getAuthorFeed", params)
        
        if not data or "feed" not in data:
            Printer.warn(f"{handle}: 未获取到数据或 API 响应异常")
            return []

        feed_items = data["feed"]
        rows = []
        
        for item in feed_items:
            video_data = self._parse_item(item, handle)
            if video_data:
                rows.append(video_data)

        # 打印结果
        if len(rows) > 0:
            print(f"   └── {Fore.GREEN}找到 {len(rows)} 个视频{Style.RESET_ALL} | {handle}")
        else:
            print(f"   └── {Fore.LIGHTBLACK_EX}无视频内容{Style.RESET_ALL} | {handle}")
            
        return rows

    def _parse_item(self, item, handle):
        """解析单条 API 数据为字典"""
        try:
            post = item.get("post", {})
            record = post.get("record", {})
            embed = post.get("embed", {})
            
            # 必须有 embed 且类型必须是视频
            if embed.get('$type') != 'app.bsky.embed.video#view':
                return None

            uri = post.get("uri", "")
            if not uri: return None
            
            post_id = uri.split("/")[-1]
            video_link = f"https://bsky.app/profile/{handle}/post/{post_id}"
            
            raw_text = record.get("text", "")
            clean_title = raw_text.replace("\n", " ").strip()[:50]
            
            raw_date = post.get("indexedAt", "")
            publish_date = raw_date.replace("T", " ").split(".")[0] if raw_date else ""
            
            v_duration = embed.get('video', {}).get('duration', 0)

            return {
                'Video File': video_link,
                'title': clean_title if clean_title else f"Video_{post_id}",
                'rawtext': raw_text,
                'translated_text': "", # 保持空字符串
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
            }
        except Exception:
            return None

# ============= 4. 数据处理与保存 =============

def merge_and_save(new_data):
    filename = CONFIG['OUTPUT_FILE']
    if not new_data:
        Printer.warn("本次运行未抓取到任何视频。")
        return

    new_df = pd.DataFrame(new_data)
    
    # 确保所有列存在
    for col in COLUMNS:
        if col not in new_df.columns: new_df[col] = ""

    # 读取旧文件
    if os.path.exists(filename):
        try:
            old_df = pd.read_excel(filename)
            old_count = len(old_df)
            
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
            # 去重：保留旧数据（防止覆盖已有的手动翻译或状态修改）
            final_df = combined_df.drop_duplicates(subset=['Video File'], keep='first')
            
            added_count = len(final_df) - old_count
            Printer.info(f"合并数据: 原有 {old_count} 条 | 新增 {added_count} 条")
        except Exception as e:
            Printer.error(f"读取旧文件失败，将覆盖: {e}")
            final_df = new_df
    else:
        Printer.info("未发现旧文件，创建新文件...")
        final_df = new_df

    # 格式化输出
    final_df = final_df[COLUMNS]
    final_df = final_df.sort_values(by='Publish Date', ascending=False)

    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        final_df.to_excel(filename, index=False)
        Printer.success(f"文件保存成功: {filename}")
        
        # --- 打印最终统计表格 ---
        print_summary(final_df)
        
    except PermissionError:
        Printer.error(f"保存失败！请先关闭 Excel 文件: {filename}")

def print_summary(df):
    """打印漂亮的终端统计表"""
    Printer.header("📊 最终结果统计")
    
    # 统计每个 channel 的视频数
    summary = df['channel_name'].value_counts().reset_index()
    summary.columns = ['Channel', 'Total Videos']
    
    print(tabulate(summary, headers='keys', tablefmt='simple_outline', showindex=False))
    print(f"\nTotal Database Size: {len(df)} records")
    print(f"{Fore.MAGENTA}{'='*50}{Style.RESET_ALL}")

# ============= 5. 主程序 =============

def main():
    start_time = time.time()
    Printer.header("🚀 Bluesky 视频抓取工具启动")
    
    fetcher = BlueskyFetcher()
    all_videos = []

    print(f"{Fore.WHITE}正在扫描 {len(CONFIG['TARGETS'])} 个目标用户...\n")

    for user in CONFIG['TARGETS']:
        # 仅获取最新的 CHECK_LIMIT 条
        videos = fetcher.get_latest_videos(user, limit=CONFIG['CHECK_LIMIT'])
        all_videos.extend(videos)
        time.sleep(0.2) 

    Printer.header(f"📥 抓取完成，准备处理数据 (共 {len(all_videos)} 条原生记录)")
    merge_and_save(all_videos)
    
    duration = time.time() - start_time
    print(f"\n✨ 全部完成，耗时: {duration:.2f} 秒")

if __name__ == "__main__":
    main()
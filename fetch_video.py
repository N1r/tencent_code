import asyncio
import aiohttp
import pandas as pd
import re
import os
import platform
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from tqdm.asyncio import tqdm
from colorama import init, Fore, Style
from tabulate import tabulate

# ============= 0. 初始化与美化工具 =============

init(autoreset=True)

class Printer:
    """负责美观的控制台输出"""
    @staticmethod
    def header(msg):
        print(f"\n{Fore.MAGENTA}{'='*50}\n   {msg}\n{'='*50}{Style.RESET_ALL}")

    @staticmethod
    def info(msg):
        tqdm.write(f"{Fore.CYAN}ℹ️  {msg}{Style.RESET_ALL}")

    @staticmethod
    def success(msg):
        tqdm.write(f"{Fore.GREEN}✅ {msg}{Style.RESET_ALL}")

    @staticmethod
    def warn(msg):
        tqdm.write(f"{Fore.YELLOW}⚠️  {msg}{Style.RESET_ALL}")

    @staticmethod
    def error(msg):
        tqdm.write(f"{Fore.RED}❌ {msg}{Style.RESET_ALL}")

    @staticmethod
    def channel_result(name, count, target):
        color = Fore.GREEN if count >= target else (Fore.YELLOW if count > 0 else Fore.LIGHTBLACK_EX)
        tqdm.write(f"   └── {color}获取 {count:>2}/{target} 个视频{Style.RESET_ALL} | {name}")

# ============= 1. 配置区域 =============

CONFIG = {
    # ⚠️ 替换 API Key
    'API_KEY': 'AIzaSyDMVvDeq4xHWFpTh5hGRiZoBettBqrSbcs', 
    
    'CHANNELS': {                                             
      'The David Pakman Show': 'UCvixJtaXuNdMPUGdOPcY8Ag',  
      #"APT News": "UCpLEtz3H0jSfEneSdf1YKnw",
      "DRM News International":"UCrvG04V6wbOau6fVJI01OlQ", 
      #"南华早报": "UC4SUWizzKc1tptprBkWjX2Q",
      'BTC': 'UCQANb2YPwAtK-IQJrLaaUFw',
     # 'NBC News': 'UCeY0bbntWzzVIaj2z3QigXg',                # 1140万订阅
     # 'CNN': 'UCupvZG-5ko_eiXAupbDfxWw',                      # 1890万订阅
     # 'Fox News': 'UCXIJgqnII2ZOINSWNOGFThA',                # 1240万订阅
      # 'ABC News': 'UCBi2mrWuNuyYy4gbM6fU18Q',                # 1780万订阅

    },

    # ✅ 核心配置：每个频道获取最新的多少个？
    'FETCH_LIMIT': 15, 
    
    # ⏱️ 时长过滤器 (单位: 秒)
    # 设定你需要的范围，程序会获取在这个范围内的最新视频
    'VIDEO_FILTERS': {
        'MIN_DURATION': 60,      # 最小 60 秒
        'MAX_DURATION': 350,    # 最大 20 分钟
    },
    
    'OUTPUT_FILE': 'batch/tasks_setting.xlsx',
    'CONCURRENT_LIMIT': 5 
}

COLUMNS = [
    'Video File', 'title', 'rawtext', 'translated_text', 
    'Publish Date', 'Replies', 'Reposts', 'viewCount', 
    'channel_name', 'duration', 'Source Language', 
    'Target Language', 'Dubbing', 'Status'
]

# ============= 2. API 交互逻辑 =============

@dataclass
class YouTubeConfig:
    API_KEY: str = CONFIG['API_KEY']
    BASE_URL: str = "https://www.googleapis.com/youtube/v3"
    # 多抓取一点做 Buffer，防止前10个里有不符合时长的
    MAX_RESULTS: int = CONFIG['FETCH_LIMIT'] + 10 
    VIDEO_FILTERS: dict = field(default_factory=lambda: CONFIG['VIDEO_FILTERS'])
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 2.0

class YouTubeAPI:
    def __init__(self, config: YouTubeConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(CONFIG['CONCURRENT_LIMIT'])

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            await asyncio.sleep(0.25)
            self.session = None

    async def _make_request(self, url: str, params: dict = None) -> Optional[dict]:
        async with self.semaphore:
            for attempt in range(self.config.MAX_RETRIES):
                try:
                    async with self.session.get(url, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status in [403, 404]:
                            return None
                except Exception:
                    pass
                await asyncio.sleep(self.config.RETRY_DELAY * (attempt + 1))
            return None

    async def get_latest_videos(self, channel_id: str, channel_name: str) -> List[Dict]:
        """获取视频，严格按照时间倒序，取前N个符合条件的"""
        
        # 1. 搜索
        search_params = {
            "part": "snippet",
            "channelId": channel_id,
            "order": "date", # 严格按日期倒序
            "maxResults": self.config.MAX_RESULTS,
            "type": "video",
            "key": self.config.API_KEY
        }
        
        search_data = await self._make_request(f"{self.config.BASE_URL}/search", search_params)
        if not search_data or 'items' not in search_data:
            Printer.channel_result(channel_name, 0, CONFIG['FETCH_LIMIT'])
            return []

        video_ids = [item['id']['videoId'] for item in search_data['items']]
        if not video_ids: 
            Printer.channel_result(channel_name, 0, CONFIG['FETCH_LIMIT'])
            return []

        # 2. 详情 (获取时长)
        videos_params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
            "key": self.config.API_KEY
        }

        videos_data = await self._make_request(f"{self.config.BASE_URL}/videos", videos_params)
        if not videos_data or 'items' not in videos_data:
            Printer.channel_result(channel_name, 0, CONFIG['FETCH_LIMIT'])
            return []

        # 3. 过滤并截取前 N 个
        valid_videos = []
        limit = CONFIG['FETCH_LIMIT']

        # 注意：API 返回的顺序可能在批量 fetch 后略微打乱，这里最好重新按时间排一下确保是 "Latest"
        items = videos_data['items']
        items.sort(key=lambda x: x['snippet']['publishedAt'], reverse=True)

        for item in items:
            if len(valid_videos) >= limit: break # 够了就停

            video = self._parse_video_data(item, channel_name)
            if video: 
                valid_videos.append(video)
        
        # 打印结果
        Printer.channel_result(channel_name, len(valid_videos), limit)
        
        return valid_videos

    def _parse_video_data(self, item: Dict, channel_name: str) -> Optional[Dict]:
        try:
            duration_str = item['contentDetails'].get('duration', 'PT0S')
            duration = self._parse_duration(duration_str)
            
            stats = item.get('statistics', {})
            view_count = int(stats.get('viewCount', 0))
            comment_count = int(stats.get('commentCount', 0))

            # 仅保留时长符合的
            if not (self.config.VIDEO_FILTERS['MIN_DURATION'] <= duration <= self.config.VIDEO_FILTERS['MAX_DURATION']):
                return None
            
            return {
                'Video File': f"https://www.youtube.com/watch?v={item['id']}",
                'title': item['snippet']['title'],
                'rawtext': item['snippet'].get('description', '')[:500],
                'translated_text': "",
                'Publish Date': item['snippet']['publishedAt'],
                'Replies': comment_count,
                'Reposts': 0,
                'viewCount': view_count,
                'channel_name': channel_name,
                'duration': duration,
                'Source Language': 'en',
                'Target Language': '简体中文',
                'Dubbing': 0,
                'Status': '',
                "Score" : 0
            }
        except Exception:
            return None

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        match = re.match(r'PT(\d+H)?(\d+M)?(\d+S)?', duration_str)
        if not match: return 0
        hours = int(match.group(1)[:-1]) if match.group(1) else 0
        minutes = int(match.group(2)[:-1]) if match.group(2) else 0
        seconds = int(match.group(3)[:-1]) if match.group(3) else 0
        return hours * 3600 + minutes * 60 + seconds

# ============= 3. 数据处理与保存 =============

class DataProcessor:
    def __init__(self, videos_data: List[Dict]):
        self.videos_data = videos_data

    def process_and_save(self):
        filename = CONFIG['OUTPUT_FILE']
        
        if not self.videos_data:
            Printer.warn("本次运行未找到符合条件的视频。")
            return

        # 直接转换为 DataFrame，不做任何随机删选
        new_df = pd.DataFrame(self.videos_data)
        
        # 确保列结构对齐
        for col in COLUMNS:
            if col not in new_df.columns: new_df[col] = ""
        new_df = new_df[COLUMNS]

        # 读取旧文件并合并
        final_df = self._merge_with_existing(new_df, filename)

        # 保存
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            final_df.to_excel(filename, index=False)
            Printer.success(f"文件保存成功: {filename}")
            
            # 打印最终统计表
            self._print_summary(final_df)
            
        except PermissionError:
            Printer.error(f"保存失败！请先关闭 Excel 文件: {filename}")

    def _merge_with_existing(self, new_df: pd.DataFrame, filename: str) -> pd.DataFrame:
        if os.path.exists(filename):
            try:
                old_df = pd.read_excel(filename)
                old_count = len(old_df)
                
                # 新数据在最后
                combined_df = pd.concat([old_df, new_df], ignore_index=True)
                # 根据 'Video File' 去重，保留 'first' (即保留旧文件里的状态)
                final_df = combined_df.drop_duplicates(subset=['Video File'], keep='first')
                
                # 重新排序：按发布时间倒序 (可选，方便查看最新)
                # 3. 计算综合互动分 (Engagement Score)
                # 这里给 转发(Reposts) 和 评论(Replies) 更高的权重，因为它们比 观看(viewCount) 更难获得
                # 公式：播放量 + 评论*5 + 转发*10 (权重可按需调整)
                final_df['Score'] = (
                    final_df['viewCount'] + 
                    final_df['Replies'] * 5 + 
                    final_df['Reposts'] * 10
                )
                # 4. 计算最终得分 (Score)
                # 采用类似 Hacker News 的经典衰减公式：Score = Engagement / (Age + 2)^Gravity
                # Gravity(重力系数) 越大，新内容排得越靠前。建议取值 1.5 到 1.8 
                final_df = final_df.sort_values(by=['Score', 'Publish Date'], ascending=[False, False])
                # 5. 排序
                #final_df = final_df.sort_values(by='Publish Date', ascending=False)

                # 计算统计信息
                total_fetched = len(new_df)
                actual_added = len(final_df) - old_count
                duplicates = total_fetched - actual_added
                
                Printer.info(f"数据合并: 库中原有 {old_count} | 本次抓取 {total_fetched} | 实际入库 {Fore.GREEN}{actual_added}{Style.RESET_ALL} | 重复忽略 {duplicates}")
                return final_df
            except Exception as e:
                Printer.error(f"读取旧文件失败: {e}，将创建新文件。")
                return new_df
        else:
            Printer.info("创建新任务文件...")
            return new_df

    def _print_summary(self, df: pd.DataFrame):
        """打印漂亮的终端统计表"""
        Printer.header("📊 最终数据库统计")
        
        # 统计每个 channel 的视频数
        summary = df['channel_name'].value_counts().reset_index()
        summary.columns = ['Channel', 'Videos in DB']
        
        print(tabulate(summary, headers='keys', tablefmt='simple_outline', showindex=False))
        print(f"\nTotal Tasks: {len(df)}")

# ============= 4. 主程序 =============

async def main():
    start_time = time.time()
    Printer.header("🚀 YouTube 最新视频抓取工具 (Top 10)")
    
    config = YouTubeConfig()
    all_videos = []
    
    print(f"{Fore.WHITE}目标频道: {len(CONFIG['CHANNELS'])} 个 | 单频道目标: 最新 {CONFIG['FETCH_LIMIT']} 条\n")

    async with YouTubeAPI(config) as api:
        tasks = [
            api.get_latest_videos(cid, name)
            for name, cid in CONFIG['CHANNELS'].items()
        ]
        
        # 进度条
        with tqdm(total=len(tasks), desc="扫描进度", unit="channel", colour='green') as pbar:
            for coro in asyncio.as_completed(tasks):
                res = await coro
                all_videos.extend(res)
                pbar.update(1)

    Printer.header(f"📥 扫描完成，准备处理数据 (共获取 {len(all_videos)} 条)")
    
    processor = DataProcessor(all_videos)
    processor.process_and_save()
    
    duration = time.time() - start_time
    print(f"\n✨ 全部完成，耗时: {duration:.2f} 秒")

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

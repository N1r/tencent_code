import asyncio
import aiohttp
import pandas as pd
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from tqdm.asyncio import tqdm
import os
import platform
import random
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CONFIG = {
    'API_KEY': 'AIzaSyDMVvDeq4xHWFpTh5hGRiZoBettBqrSbcs',
    #'API_KEY': 'AIzaSyABmSbMC15Uf0xVn6NWzNpUG9b9l3a5yaY', 
    'CHANNELS': {
        # === 顶级高频源（日更10-20条）===
        'MeidasTouch': 'UC9r9HYFxEQOBXSopFS61ZWg',              # 570万订阅，反特朗普
        #'The Hill': 'UCPWXiRWZ29zrxPFIQT7eHSA',                # 270万订阅，独立新闻
       # 'Forbes Breaking News': 'UCuTiq7iBWzbKfvTqNhUz7bg',    # 国会听证剪辑
        #'Tucker Carlson': 'UCxwubvG70lardn6CkfVdnSw',          # 175万订阅，保守派
        
        # === 主流媒体（日更5-10条）===
        #'NBC News': 'UCeY0bbntWzzVIaj2z3QigXg',                # 1140万订阅
        'CNN': 'UCupvZG-5ko_eiXAupbDfxWw',                      # 1890万订阅
        'Fox News': 'UCXIJgqnII2ZOINSWNOGFThA',                # 1240万订阅
        #'ABC News': 'UCBi2mrWuNuyYy4gbM6fU18Q',                # 1780万订阅
        
        # === 国会/专题===
        'The Hill': 'UCPWXiRWZ29zrxPFIQT7eHSA',
        'Forbes Breaking News': 'UCg40OxZ1GYh3u3jBntB6DLg',  # 原ID: UCg40OxZ1GYh3u3jBntB6DLg
        'Congress Clips': 'UUJQFbOJfbN6ZjJ3R5AvxNyg',  # 原ID: UCJQFbOJfbN6ZjJ3R5AvxNyg
        'The Stephen A. Smith Show': 'UU2OREBiIbDChxvmDeg30Bsg',  # 原ID: UC2OREBiIbDChxvmDeg30Bsg
        'Benny Johnson': 'UULdP3jmBYe9lAZQbY6OSYjw',  # 原ID: UCLdP3jmBYe9lAZQbY6OSYjw
 
        # === 个人主播（日更3-8条）===
        'BTC': 'UCQANb2YPwAtK-IQJrLaaUFw',                      # Brian Tyler Cohen，左翼
        #'Ben Shapiro': 'UCnQC_G5Xsjhp9fEJKuIcrSw',             # 650万订阅，右翼
        'Benny Johnson': 'UCfiCnGMHYrEWU97NAdzQ1Fw',           # 保守派Meme
        'The David Pakman Show': 'UCvixJtaXuNdMPUGdOPcY8Ag',   # 220万订阅，进步派
    },
    
    'MAX_RESULTS_PER_CHANNEL': 10,
    
    'VIDEO_FILTERS': {
        'MIN_DURATION': 150,      # 2分钟
        'MAX_DURATION': 500,      # 10分钟
        'MIN_VIEWS': 1000,
        'MIN_COMMENTS': 10
    },
    
    'SELECTION': {
        'NUM_CHANNELS': 10,                    # 随机选择的频道数
        'VIDEOS_PER_CHANNEL_MIN': 1,          # 每个频道最少视频数
        'VIDEOS_PER_CHANNEL_MAX': 2,          # 每个频道最多视频数
        'TOP_N_CANDIDATES': 5                # 从每个频道评论数前N名中选择
    }
}
@dataclass
class YouTubeConfig:
    API_KEY: str = CONFIG['API_KEY']
    BASE_URL: str = "https://www.googleapis.com/youtube/v3"
    MAX_RESULTS: int = CONFIG['MAX_RESULTS_PER_CHANNEL']
    VIDEO_FILTERS: dict = field(default_factory=lambda: CONFIG['VIDEO_FILTERS'])
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 2.0

class YouTubeAPI:
    def __init__(self, config: YouTubeConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            await asyncio.sleep(0.25)  # 确保连接完全关闭
            self.session = None

    async def _make_request(self, url: str, params: dict = None) -> Optional[dict]:
        """带重试机制的HTTP请求"""
        for attempt in range(self.config.MAX_RETRIES):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'error' in data:
                            logger.error(f"API Error: {data['error']['message']}")
                            return None
                        return data
                    elif response.status == 403:
                        logger.error("API quota exceeded or invalid API key")
                        return None
                    else:
                        logger.warning(f"HTTP {response.status}, retrying... ({attempt + 1}/{self.config.MAX_RETRIES})")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on attempt {attempt + 1}/{self.config.MAX_RETRIES}")
            except Exception as e:
                logger.error(f"Request failed: {e}")
            
            if attempt < self.config.MAX_RETRIES - 1:
                await asyncio.sleep(self.config.RETRY_DELAY * (attempt + 1))
        
        return None

    async def get_latest_videos(self, channel_id: str, channel_name: str, max_results: int = 10) -> List[Dict[Any, Any]]:
        """获取频道最新视频"""
        logger.info(f"Fetching videos from: {channel_name}")
        
        # 第一步：搜索最新视频
        search_url = f"{self.config.BASE_URL}/search"
        search_params = {
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "maxResults": max_results,
            "type": "video",
            "key": self.config.API_KEY
        }
        
        search_data = await self._make_request(search_url, search_params)
        if not search_data or 'items' not in search_data:
            logger.warning(f"No videos found for {channel_name}")
            return []

        video_ids = [
            item['id']['videoId']
            for item in search_data['items']
            if item['id']['kind'] == 'youtube#video'
        ]

        if not video_ids:
            return []

        # 第二步：获取视频详细信息
        videos_url = f"{self.config.BASE_URL}/videos"
        videos_params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
            "key": self.config.API_KEY
        }

        videos_data = await self._make_request(videos_url, videos_params)
        if not videos_data or 'items' not in videos_data:
            return []

        videos = []
        for item in videos_data['items']:
            video = self._parse_video_data(item, channel_name)
            if video:
                videos.append(video)
        
        logger.info(f"Found {len(videos)} valid videos from {channel_name}")
        return videos

    def _parse_video_data(self, item: Dict, channel_name: str) -> Optional[Dict]:
        """解析视频数据"""
        try:
            duration = self._parse_duration(item['contentDetails'].get('duration', 'PT0S'))
            view_count = int(item['statistics'].get('viewCount', 0))
            comment_count = int(item['statistics'].get('commentCount', 0))

            # 检查是否符合筛选条件
            if not self._meets_criteria(duration, view_count, comment_count):
                return None

            return {
                'videoId': item['id'],
                'title': item['snippet']['title'],
                'description': item['snippet']['description'][:200],  # 限制描述长度
                'publishedAt': item['snippet']['publishedAt'],
                'duration': duration,
                'viewCount': view_count,
                'commentCount': comment_count,
                'channel_name': channel_name,
            }
        except Exception as e:
            logger.error(f"Error parsing video data: {e}")
            return None

    def _meets_criteria(self, duration: int, views: int, comments: int) -> bool:
        """检查视频是否符合筛选条件"""
        filters = self.config.VIDEO_FILTERS
        return (
            filters['MIN_DURATION'] <= duration <= filters['MAX_DURATION'] and
            views >= filters['MIN_VIEWS'] and
            comments >= filters['MIN_COMMENTS']
        )

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """解析ISO 8601时长格式"""
        hours = minutes = seconds = 0
        duration_str = duration_str.replace('PT', '')
        
        if 'H' in duration_str:
            parts = duration_str.split('H')
            hours = int(parts[0])
            duration_str = parts[1]
        
        if 'M' in duration_str:
            parts = duration_str.split('M')
            minutes = int(parts[0])
            duration_str = parts[1]
        
        if 'S' in duration_str:
            seconds = int(duration_str.replace('S', ''))
        
        return hours * 3600 + minutes * 60 + seconds

class YouTubeDataProcessor:
    def __init__(self, videos_data: List[Dict]):
        self.videos_data = [v for v in videos_data if v is not None]

    def process_data(self) -> pd.DataFrame:
        """处理视频数据并生成Excel"""
        if not self.videos_data:
            logger.warning("No videos to process")
            return pd.DataFrame()

        df = pd.DataFrame(self.videos_data)
        logger.info(f"Total videos before filtering: {len(df)}")
        
        # 添加必需列
        df['Video File'] = 'https://www.youtube.com/watch?v=' + df['videoId']
        df['Source Language'] = 'en'
        df['Target Language'] = '简体中文'
        df['Dubbing'] = 0
        df['Status'] = ''

        # 保存完整数据集
        df_full = df.copy()
        df_full.to_excel('batch/all_videos.xlsx', index=False)
        logger.info(f"Saved full dataset: batch/all_videos.xlsx ({len(df_full)} videos)")

        # 智能选择视频
        df_selected = self._smart_selection(df)
        
        # 合并现有数据
        df_final = self._merge_with_existing(df_selected)
        
        return df_final[['Video File', 'title', 'description', 'viewCount', 
                        'channel_name', 'duration', 'Source Language', 
                        'Target Language', 'Dubbing', 'Status']]

    def _smart_selection(self, df: pd.DataFrame) -> pd.DataFrame:
        """智能选择视频"""
        config = CONFIG['SELECTION']
        
        # 随机选择频道
        unique_channels = df['channel_name'].unique()
        num_channels = min(config['NUM_CHANNELS'], len(unique_channels))
        selected_channels = random.sample(list(unique_channels), num_channels)
        
        logger.info(f"Selected {num_channels} channels: {', '.join(selected_channels)}")
        
        # 从每个频道选择视频
        df_filtered = df[df['channel_name'].isin(selected_channels)].copy()
        
        # 按频道和评论数排序
        df_filtered = df_filtered.sort_values(
            by=['channel_name', 'commentCount'], 
            ascending=[True, False]
        )
        
        # 从每个频道的前N名中随机选择1-2个
        selected_videos = []
        for channel in selected_channels:
            channel_videos = df_filtered[df_filtered['channel_name'] == channel]
            
            # 获取前N个候选视频
            candidates = channel_videos.head(config['TOP_N_CANDIDATES'])
            
            # 随机选择1-2个
            n_select = min(
                random.randint(config['VIDEOS_PER_CHANNEL_MIN'], config['VIDEOS_PER_CHANNEL_MAX']),
                len(candidates)
            )
            
            selected = candidates.sample(n=n_select)
            selected_videos.append(selected)
            
            logger.info(f"  {channel}: selected {n_select} from {len(candidates)} candidates")
        
        # 合并并打乱顺序
        df_result = pd.concat(selected_videos, ignore_index=True)
        df_result = df_result.sample(frac=1).reset_index(drop=True)
        
        # 保存本次新选择的视频
        df_result.to_excel('batch/new_videos.xlsx', index=False)
        logger.info(f"Saved newly selected videos: batch/new_videos.xlsx ({len(df_result)} videos)")
        
        return df_result

    def _merge_with_existing(self, df_new: pd.DataFrame) -> pd.DataFrame:
        """与现有数据合并"""
        try:
            existing_df = pd.read_excel('batch/tasks_setting.xlsx')
            logger.info(f"Found existing tasks file with {len(existing_df)} entries")
            
            # 合并数据
            df_combined = pd.concat([existing_df, df_new], ignore_index=True)
            
            # 去重
            df_combined = df_combined.drop_duplicates(subset=['Video File'], keep='first')
            
            logger.info(f"After merging and deduplication: {len(df_combined)} videos")
            return df_combined
            
        except FileNotFoundError:
            logger.info("No existing tasks file found, creating new one")
            return df_new
        except Exception as e:
            logger.error(f"Error merging with existing file: {e}")
            return df_new

async def main():
    """主函数"""
    config = YouTubeConfig()
    channels = CONFIG['CHANNELS']

    # 创建输出目录
    os.makedirs('batch', exist_ok=True)

    logger.info(f"Starting to fetch data for {len(channels)} channels...")
    logger.info(f"Video filters: {CONFIG['VIDEO_FILTERS']}")

    async with YouTubeAPI(config) as api:
        # 创建任务列表
        tasks = [
            api.get_latest_videos(channel_id, channel_name, CONFIG['MAX_RESULTS_PER_CHANNEL'])
            for channel_name, channel_id in channels.items()
        ]
        
        # 使用进度条执行任务
        all_videos_data = []
        with tqdm(total=len(tasks), desc="Fetching channels") as pbar:
            for coro in asyncio.as_completed(tasks):
                videos = await coro
                all_videos_data.append(videos)
                pbar.update(1)

        # 展平视频列表
        all_videos = [video for videos in all_videos_data for video in videos]
        logger.info(f"Total videos fetched: {len(all_videos)}")

        # 处理数据
        logger.info("Processing video data...")
        processor = YouTubeDataProcessor(all_videos)
        df = processor.process_data()

        # 保存结果
        output_path = 'batch/tasks_setting.xlsx'
        df.to_excel(output_path, index=False)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"✅ Successfully processed {len(df)} videos")
        logger.info(f"📁 Results saved to: {output_path}")
        logger.info(f"{'='*50}\n")

if __name__ == "__main__":
    # Windows兼容性设置
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 运行主程序
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)

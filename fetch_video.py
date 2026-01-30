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

# ============= 1. 配置区域 =============

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CONFIG = {
    'API_KEY': 'AIzaSyDMVvDeq4xHWFpTh5hGRiZoBettBqrSbcs', # 请确保您的 API Key 有效
    'CHANNELS': {                                             
      #'MeidasTouch': 'UC9r9HYFxEQOBXSopFS61ZWg',            
      #'CNN': 'UCupvZG-5ko_eiXAupbDfxWw',                    
      #'Fox News': 'UCXIJgqnII2ZOINSWNOGFThA',               
      #'The Hill': 'UCPWXiRWZ29zrxPFIQT7eHSA',               
      #'Forbes Breaking News': 'UCg40OxZ1GYh3u3jBntB6DLg',   
      #'Congress Clips': 'UUJQFbOJfbN6ZjJ3R5AvxNyg',         
      #'Benny Johnson': 'UULdP3jmBYe9lAZQbY6OSYjw',          
      'The David Pakman Show': 'UCvixJtaXuNdMPUGdOPcY8Ag',  
      #'Associated Press': 'UC52X5wxOL_s5yw0dQk7NtgA',  
      "APT News": "UCpLEtz3H0jSfEneSdf1YKnw",
      "DRM News International":"UCrvG04V6wbOau6fVJI01OlQ", 
      #'MS NOW': 'UCaXkIU1QidjPwiAYu6GcHjg',                 
      #'Global News': 'UChLtXXpo4Ge1ReTEboVvTDg',
      "南华早报": "UC4SUWizzKc1tptprBkWjX2Q",
      #"TBS NEWS DIG" : "UC6AG81pAkf6Lbi_1VC5NmPA",
      #"The Dodo":"UCINb0wqPz-A0dV9nARjJlOQ",      
      #'Luke Beasley': 'UCM05jgFNwoeXvWfO9GuExzA',           
      #'Jimmy Kimmel Live': 'UCa6vGFO9ty8v5KZJXQxdhaw',      
      #'The Economist': 'UC0p5jTq6Xx_DosDFxVXnWaQ',          
      #'The Daily Show': 'UCwWhs_6x42TyRM4Wstoq8HA',         
      #'Tucker Carlson': 'UCxwubvG70lardn6CkfVdnSw',          # 175万订阅，保守派
      'BTC': 'UCQANb2YPwAtK-IQJrLaaUFw',                      # Brian Tyler Cohen，左翼
      #'The Stephen A. Smith Show': 'UU2OREBiIbDChxvmDeg30Bsg',  # 原ID: UC2OREBiIbDChxvmDeg30Bsg
    },
    # Shorts 更新频率快，建议单频道检索量加大
    'MAX_RESULTS_PER_CHANNEL': 15, 
    
    'VIDEO_FILTERS': {
        'MIN_DURATION': 150,      # 至少5秒
        'MAX_DURATION': 450,     # 【关键】YouTube Shorts 严格限制在 60 秒以内
        'MIN_VIEWS': 5000,      # Shorts 播放量基数通常较大，可适当调高
        'MIN_COMMENTS': 1      # 互动过滤
    },
    
    'SELECTION': {
        'NUM_CHANNELS': 10,                    
        'VIDEOS_PER_CHANNEL_MIN': 1,          
        'VIDEOS_PER_CHANNEL_MAX': 3,          # 每个频道多选几个，Shorts 消耗快
        'TOP_N_CANDIDATES': 10,                # 从评论数前10名中筛选
    }
}

# ============= 2. 数据模型与 API 类 =============

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
            await asyncio.sleep(0.25)
            self.session = None

    async def _make_request(self, url: str, params: dict = None) -> Optional[dict]:
        for attempt in range(self.config.MAX_RETRIES):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 403:
                        logger.error("API 额度超限或 Key 无效")
                        return None
            except Exception as e:
                logger.error(f"请求失败: {e}")
            await asyncio.sleep(self.config.RETRY_DELAY * (attempt + 1))
        return None

    async def get_latest_videos(self, channel_id: str, channel_name: str, max_results: int = 20) -> List[Dict]:
        """获取频道最新 Shorts"""
        logger.info(f"正在从频道抓取 Shorts: {channel_name}")
        
        # 第一步：搜索（使用 videoDuration='short' 过滤 4 分钟以下视频）
        search_params = {
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "maxResults": max_results,
            "type": "video",
            "key": self.config.API_KEY
        }
        
        search_data = await self._make_request(f"{self.config.BASE_URL}/search", search_params)
        if not search_data or 'items' not in search_data:
            return []

        video_ids = [item['id']['videoId'] for item in search_data['items']]
        if not video_ids: return []

        # 第二步：获取详细统计信息
        videos_params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
            "key": self.config.API_KEY
        }

        videos_data = await self._make_request(f"{self.config.BASE_URL}/videos", videos_params)
        if not videos_data or 'items' not in videos_data:
            return []

        valid_videos = []
        for item in videos_data['items']:
            video = self._parse_video_data(item, channel_name)
            if video: valid_videos.append(video)
        
        return valid_videos

    def _parse_video_data(self, item: Dict, channel_name: str) -> Optional[Dict]:
        try:
            duration = self._parse_duration(item['contentDetails'].get('duration', 'PT0S'))
            view_count = int(item['statistics'].get('viewCount', 0))
            comment_count = int(item['statistics'].get('commentCount', 0))

            # 严格按照 60 秒过滤 Shorts
            if not (self.config.VIDEO_FILTERS['MIN_DURATION'] <= duration <= self.config.VIDEO_FILTERS['MAX_DURATION']):
                return None
            if view_count < self.config.VIDEO_FILTERS['MIN_VIEWS']:
                return None

            return {
                'videoId': item['id'],
                'title': item['snippet']['title'],
                'description': item['snippet']['description'][:200],
                'publishedAt': item['snippet']['publishedAt'],
                'duration': duration,
                'viewCount': view_count,
                'commentCount': comment_count,
                'channel_name': channel_name,
            }
        except Exception: return None

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        import re
        hours = re.search(r'(\d+)H', duration_str)
        minutes = re.search(r'(\d+)M', duration_str)
        seconds = re.search(r'(\d+)S', duration_str)
        return (int(hours.group(1)) * 3600 if hours else 0) + \
               (int(minutes.group(1)) * 60 if minutes else 0) + \
               (int(seconds.group(1)) if seconds else 0)

# ============= 3. 数据处理器 =============

class YouTubeDataProcessor:
    def __init__(self, videos_data: List[Dict]):
        self.videos_data = videos_data

    def process_data(self) -> pd.DataFrame:
        if not self.videos_data:
            logger.warning("没有采集到符合条件的 Shorts 视频")
            return pd.DataFrame()

        df = pd.DataFrame(self.videos_data)
        
        # 【关键】修改为 Shorts 专用 URL 格式
        df['Video File'] = 'https://www.youtube.com/shorts/' + df['videoId']
        df['Source Language'] = 'en'
        df['Target Language'] = '简体中文'
        df['Dubbing'] = 0
        df['Status'] = ''

        # 1. 保存所有抓取到的 Shorts (全量表)
        os.makedirs('batch', exist_ok=True)
        df.to_excel('batch/all_shorts_found.xlsx', index=False)

        # 2. 智能筛选本次任务
        df_selected = self._smart_selection(df)
        
        # 3. 合并到现有的任务清单
        return self._merge_with_existing(df_selected)

    def _smart_selection(self, df: pd.DataFrame) -> pd.DataFrame:
        config = CONFIG['SELECTION']
        unique_channels = df['channel_name'].unique()
        selected_channels = random.sample(list(unique_channels), min(config['NUM_CHANNELS'], len(unique_channels)))
        
        results = []
        for channel in selected_channels:
            candidates = df[df['channel_name'] == channel].sort_values(by='commentCount', ascending=False)
            top_pool = candidates.head(config['TOP_N_CANDIDATES'])
            
            n_select = min(random.randint(config['VIDEOS_PER_CHANNEL_MIN'], config['VIDEOS_PER_CHANNEL_MAX']), len(top_pool))
            results.append(top_pool.sample(n=n_select))
        
        return pd.concat(results).sample(frac=1).reset_index(drop=True)

    def _merge_with_existing(self, df_new: pd.DataFrame) -> pd.DataFrame:
        target_file = 'batch/tasks_setting.xlsx'
        try:
            existing_df = pd.read_excel(target_file)
            combined = pd.concat([existing_df, df_new], ignore_index=True)
            return combined.drop_duplicates(subset=['Video File'], keep='first')
        except: return df_new

# ============= 4. 运行入口 =============

async def main():
    config = YouTubeConfig()
    os.makedirs('batch', exist_ok=True)

    async with YouTubeAPI(config) as api:
        tasks = [
            api.get_latest_videos(cid, name, CONFIG['MAX_RESULTS_PER_CHANNEL'])
            for name, cid in CONFIG['CHANNELS'].items()
        ]
        
        results = []
        with tqdm(total=len(tasks), desc="抓取 Shorts 进度") as pbar:
            for coro in asyncio.as_completed(tasks):
                res = await coro
                results.extend(res)
                pbar.update(1)

        processor = YouTubeDataProcessor(results)
        df_final = processor.process_data()

        if not df_final.empty:
            df_final[['Video File', 'title', 'description', 'viewCount', 
                     'channel_name', 'duration', 'Source Language', 
                     'Target Language', 'Dubbing', 'Status']].to_excel('batch/tasks_setting.xlsx', index=False)
            logger.info(f"✅ 成功提取 {len(df_final)} 条任务到 batch/tasks_setting.xlsx")

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

import asyncio
import aiohttp
import pandas as pd
from typing import List, Dict, Any
from dataclasses import dataclass, field
from tqdm.asyncio import tqdm
import os
import platform
import requests  # 新增 requests 库
import random

# 确保 openpyxl 已安装
# pip install openpyxl

# YouTube API Configuration
CONFIG = {
    'API_KEY': 'AIzaSyDMVvDeq4xHWFpTh5hGRiZoBettBqrSbcs',
    'CHANNELS': {
        #'CNN': 'UCupvZG-5ko_eiXAupbDfxWw',         # CNN Official Channel
        #'MSNBC': 'UCaXkIU1QidjPwiAYu6GcHjg',       
        #'FoxNews': 'UCXIJgqnII2ZOINSWNOGFThA',
        #'ABCNews': 'UCBi2mrWuNuyYy4gbM6fU18Q',
        #'CBSNews': 'UC8p1vwvWtl6T73JiExfWs1g',
        'Tucker Carlson Network': 'UCGttrUON87gWfU6dMWm1fcA',
        #'The Young Turks': 'UC1yBKRuGpC1tSM73A0ZjYjQ',
        'Late Night with Seth Meyers': 'UCVTyTA7-g9nopHeHbeuvpRA',
        'BillOReilly': 'UC4OvD2yIbofl9l4dIlqSNMw',
        'thedavidpakmanshow': 'UCvixJtaXuNdMPUGdOPcY8Ag',
        #'MeidasTouch': 'UC9r9HYFxEQOBXSopFS61ZWg',
        'briantylercohen': 'UCQANb2YPwAtK-IQJrLaaUFw',
        #'TCNetwork': 'UCXieXRA4Sr_YOrAmzIN2EgQ',
        'Inside_China_Business': 'UCNlAaPtfHizB_k6wztaHmZg',
        #'ponderingpolitics': 'UCbU6Rve0XMNZ2a2yaYgjlTA',
        #'realchris': 'UCcHV234NEAIv-ifDcgZfBfw',
        #'omaragamyy': 'UCbmOgzvvDg60mXGm9t9Ad5Q',
        #'CNBC': 'UCvJJ_dzjViJCoLf5uKUTwoA',
        #'VALUETAINMENT': 'UCIHdDJ0tjn_3j-FS7s_X1kQ',
        #'CNBCtelevision': 'UCrp_UI8XtuYfpiqluWLD7Lw',
        #'NewsNation': 'UCCjG8NtOig0USdrT5D1FpxQ',
        #'dwnews': 'UCknLrEdhRCp1aegoMqRaCZg',
        #'BBCNews': 'UC16niRr50-MSBwiO3YDb3RA',
        #'aljazeeraenglish': 'UCNye-wNBqNL5ZzHSJj3l8Bg',
        #'themoverandgonkyshow': 'UCfFDIa-yhj80tl8WQ5e2IMQ',
        #'Tucker Carlson Network': 'UCGttrUON87gWfU6dMWm1fcA',
        #'Al Jazeera English': 'UCNye-wNBqNL5ZzHSJj3l8Bg',
        #'Novara Media': 'UCOzMAa6IhV6uwYQATYG_2kg',
        },
    'MAX_RESULTS_PER_CHANNEL': 10,  # 修改为获取最新视频的数量
    'VIDEO_FILTERS': {
        'MIN_DURATION': 180,
        'MAX_DURATION': 500,
        'MIN_VIEWS': 1000,
        'MIN_COMMENTS': 10
    }
}

@dataclass
class YouTubeConfig:
    API_KEY: str = CONFIG['API_KEY']
    BASE_URL: str = "https://www.googleapis.com/youtube/v3"
    MAX_RESULTS: int = CONFIG['MAX_RESULTS_PER_CHANNEL']
    VIDEO_FILTERS: dict = field(default_factory=lambda: CONFIG['VIDEO_FILTERS'])

class YouTubeAPI:
    def __init__(self, config: YouTubeConfig):
        self.config = config
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None  # 确保会话被清除

    async def get_latest_videos(self, channel_id: str, max_results: int = 10) -> List[Dict[Any, Any]]:
        search_url = f"{self.config.BASE_URL}/search?part=snippet&channelId={channel_id}&order=date&maxResults={max_results}&key={self.config.API_KEY}"
        async with self.session.get(search_url) as response:
            search_data = await response.json()
            if 'error' in search_data:
                print(f"Error fetching videos for channel {channel_id}: {search_data['error']['message']}")
                return []

            video_ids = [
                item['id']['videoId']
                for item in search_data.get('items', [])
                if item['id']['kind'] == 'youtube#video'
            ]

        if not video_ids:
            return []

        videos_params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
            "key": self.config.API_KEY
        }

        async with self.session.get(f"{self.config.BASE_URL}/videos", params=videos_params) as response:
            videos_data = await response.json()
            if 'error' in videos_data:
                print(f"Error fetching video details: {videos_data['error']['message']}")
                return []

            videos = [self._parse_video_data(item) for item in videos_data.get('items', [])]
            return [v for v in videos if v is not None]

    def _parse_video_data(self, item: Dict) -> Dict:
        try:
            duration = self._parse_duration(item['contentDetails'].get('duration', 'PT0S'))
            view_count = int(item['statistics'].get('viewCount', 0))
            comment_count = int(item['statistics'].get('commentCount', 0))

            if not self._meets_criteria(duration, view_count, comment_count):
                return None

            return {
                'videoId': item['id'],
                'title': item['snippet']['title'],
                'description': item['snippet']['description'].split('\n')[0],
                'publishedAt': item['snippet']['publishedAt'],
                'duration': duration,
                'viewCount': view_count,
                'commentCount': comment_count,
                'channel_name': item['snippet']['channelTitle'],
            }
        except Exception as e:
            print(f"Error parsing video data: {e}")
            return None

    def _meets_criteria(self, duration: int, views: int, comments: int) -> bool:
        filters = self.config.VIDEO_FILTERS
        return (filters['MIN_DURATION'] <= duration <= filters['MAX_DURATION'] and
                views >= filters['MIN_VIEWS'] and
                comments >= filters['MIN_COMMENTS'])

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        hours = minutes = seconds = 0
        if 'H' in duration_str:
            hours = int(duration_str.split('H')[0].replace('PT', ''))
            duration_str = duration_str.split('H')[1]
        if 'M' in duration_str:
            minutes = int(duration_str.split('M')[0].replace('PT', ''))
            duration_str = duration_str.split('M')[1]
        if 'S' in duration_str:
            seconds = int(duration_str.split('S')[0].replace('PT', ''))
        return hours * 3600 + minutes * 60 + seconds

class YouTubeDataProcessor:
    def __init__(self, videos_data: List[Dict]):
        self.videos_data = [v for v in videos_data if v is not None]

    def process_data(self) -> pd.DataFrame:
        if not self.videos_data:
            return pd.DataFrame()

        df = pd.DataFrame(self.videos_data)
        df['Video File'] = 'https://www.youtube.com/watch?v=' + df['videoId']

        # Add required columns
        df['Source Language'] = 'en'
        df['Target Language'] = '简体中文'
        df['Dubbing'] = 0
        df['Status'] = ''

        # Save full dataset
        df_full = df.copy()
        df_full.to_excel('batch/all_videos.xlsx', index=False)

        try:
            # 读取现有的 Excel 文件
            existing_df = pd.read_excel('batch/tasks_setting.xlsx')
            print(f"Found existing tasks file with {len(existing_df)} entries")

            # 确保列名一致
            if not set(existing_df.columns) == set(df.columns):
                print("列名不一致，请检查数据格式！")

            # # 合并现有数据和新数据
            # df = df.sort_values(by=['channel_name', 'viewCount', 'commentCount'],
            #                 ascending=[True, False, False])
                            
            # df = df.groupby('channel_name').apply(lambda x: x.sample(n=min(1, len(x)))).reset_index(drop=True)
            # 按 'channel_name' 分组，并获取每个频道播放量最高的前两个视频



            # 首先随机选择5个频道
            unique_channels = df['channel_name'].unique()
            selected_channels = random.sample(list(unique_channels), min(8, len(unique_channels)))
#            df = df.sort_values(by=['channel_name', 'commentCount'], ascending=[True, False]) #降序
            # 从每个频道的前3-5名中随机选择1-2个
            # df = df.groupby('channel_name').apply(
            #     lambda x: x.head(min(5, len(x))).sample(n=min(random.randint(1, 2), len(x.head(min(5, len(x))))))
            # ).reset_index(drop=True)
            df = (
                df[df['channel_name'].isin(selected_channels)]
                .sort_values(by=['channel_name', 'commentCount'], ascending=[True, False])
                .groupby('channel_name', group_keys=False)  # 避免多重索引
                .apply(lambda x: x.head(min(10, len(x))).sample(n=min(random.randint(1, 2), len(x))))
                .sample(frac=1)  # 全局随机打乱顺序
                .reset_index(drop=True)
            )
            # df = (
            #     df[df['channel_name'].isin(selected_channels)]
            #     .sort_values(by=['channel_name', 'commentCount'], ascending=[True, False])
            #     .groupby('channel_name', group_keys=False)  # 避免多重索引
            #     .apply(lambda x: x.head(min(5, len(x))).sample(n=min(random.randint(1, 5), len(x))))
            #     .reset_index(drop=True)
            # )
            
            # df = (df[df['channel_name'].isin(selected_channels)]
            #     .sort_values(by=['channel_name', 'commentCount'], ascending=[True, False])
            #     .groupby('channel_name')
            #     .apply(lambda x: x.head(min(5, len(x))).sample(n=min(random.randint(1,2), len(x.head(min(3, len(x)))))), 
            #     #.apply(lambda x: x.head(min(5, len(x))).sample(n=1, len(x.head(min(3, len(x)))), 
            #             include_groups=False)  # 添加这个参数
            #     .reset_index(drop=True))

            df_temp = df.copy()
            df_temp.to_excel('batch/new_videos.xlsx', index=False)

            df = pd.concat([existing_df, df], ignore_index=True)
            # 删除重复项，基于 'Video File' 列
            df = df.drop_duplicates(subset=['Video File'], keep='first')

            print(f"合并后数据条数: {len(df)}")
        except FileNotFoundError:
            print("No existing tasks file found, creating new one")
        except Exception as e:
            print(f"Error reading existing file: {e}")

        return df[['Video File', 'title', 'description', 'viewCount', 'channel_name',
                  'duration', 'Source Language', 'Target Language', 'Dubbing', 'Status']]

async def main():
    config = YouTubeConfig()
    channel_ids = list(CONFIG['CHANNELS'].values())

    # Create batch directory if it doesn't exist
    os.makedirs('batch', exist_ok=True)

    print(f"Starting to fetch data for {len(channel_ids)} channels...")

    async with YouTubeAPI(config) as api:
        progress = tqdm(total=len(channel_ids), desc="Fetching channel data")
        tasks = [api.get_latest_videos(channel_id, max_results=CONFIG['MAX_RESULTS_PER_CHANNEL']) for channel_id in channel_ids]
        all_videos_data = await asyncio.gather(*tasks)
        progress.close()

        all_videos = [video for videos in all_videos_data for video in videos]

        print("\nProcessing video data...")
        processor = YouTubeDataProcessor(all_videos)
        df = processor.process_data()

        output_path = 'batch/tasks_setting.xlsx'
        df.to_excel(output_path, index=False)
        print(f'\nSuccessfully processed {len(df)} videos')
        print(f'Results saved to: {output_path}')

    # 确保所有异步任务完成
    await asyncio.sleep(0)

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
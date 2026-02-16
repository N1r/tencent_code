import pandas as pd
import requests
import json
import re
import time
from datetime import datetime

# ==========================================
# 1. 配置区域
# ==========================================

# --- API 配置 (使用您提供的参数) ---
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai' 
API_MODEL = 'qwen3-max-2026-01-23'  # 您的首选模型

# --- 文件配置 ---
INPUT_FILE = 'tasks_setting.xlsx'
OUTPUT_FILE = f'curated_output_{datetime.now().strftime("%Y%m%d")}.csv'

# --- 敏感词库 (本地预过滤，省钱且合规) ---
# 如果原文包含这些词，直接跳过，不调用 API
SENSITIVE_KEYWORDS = [
    # 政治/分裂敏感
    "Free Tibet", "Taiwan Independence", "Xi", "Fa Lun",
    # 极端内容
    "Porn", "Hentai", "Beheading", "Terrorist recruitment",
    # 侮辱性词汇
    "Chink", "Chinaman"
]

# ==========================================
# 2. 核心功能类
# ==========================================

class SensitiveFilter:
    """本地敏感词过滤，用于节省 API 额度并确保安全"""
    def __init__(self, keywords):
        self.keywords = [k.lower() for k in keywords]
    
    def check(self, text):
        if not isinstance(text, str):
            return False, None
        text_lower = text.lower()
        for kw in self.keywords:
            if kw in text_lower:
                return True, kw
        return False, None

class VideoCurator:
    def __init__(self, filepath):
        self.filepath = filepath
        self.filter = SensitiveFilter(SENSITIVE_KEYWORDS)
        self.df = None

    def load_data(self):
        """加载 CSV 数据"""
        try:
            #self.df = pd.read_csv(self.filepath, encoding='utf-8')
            self.df = pd.read_excel(self.filepath)

        except UnicodeDecodeError:
            try:
                self.df = pd.read_csv(self.filepath, encoding='latin1')
            except:
                print("❌ 文件编码错误，请确保是 UTF-8 或 CSV 格式")
                return False
        
        # 数据清洗
        self.df['rawtext'] = self.df['rawtext'].fillna('')
        self.df['title'] = self.df['title'].fillna('')
        self.df['viewCount'] = pd.to_numeric(self.df['viewCount'], errors='coerce').fillna(0)
        
        print(f"✅ 数据加载成功：共 {len(self.df)} 条记录")
        return True

    def call_ai_analysis(self, row_data):
        """
        整合了您的 API 调用逻辑 + 筛选打分逻辑
        """
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }

        # --- 构造 Prompt (结合了您的B站编辑风格 + 筛选需求) ---
        # 我们要求 AI 返回 JSON，包含：分数、分类、以及您要求的“具体化标题”
        system_prompt = """
# Role
你是一名追求“高信息密度”的B站国际时政与体育区资深编辑。
你的任务是阅读一段视频素材，判断其对中国观众的吸引力，并起一个具体的标题。

# Task
1. **评分 (score)**: 0-10分。
   - 9-10分 (S级): 涉及NBA顶流(库里/詹姆斯/内讧)、美国内乱(ICE暴力/零元购)、萝莉岛(Epstein)、中国相关(China)、马斯克。
   - 7-8分 (A级): 知名政客(特朗普)的惊人语录、科技圈大瓜。
   - 0-5分 (低价值): 无聊的会议记录、不知名路人采访、普通广告。

2. **分类 (category)**: 从 [NBA体育, 美国内政, 社会冲突, 科技财经, 其他] 中选一个。

3. **起标题 (filename)**: **核心要求：拒绝笼统，必须具体（Granularity）**。
   - 必须从文中提取**具体的名词、数据、比喻或特定事件**。
   - 格式：具象化细节/核心逻辑/经典语句。
   - 示例：勇士队主教练科尔吐槽裁判/特朗普为了省水把发型洗塌了。

# Output Format
请仅输出纯 JSON 格式，不要包含 Markdown 标记：
{
    "score": <int>,
    "category": "<str>",
    "filename": "<str>",
    "reason": "<简短评价>"
}
"""
        
        # 拼装输入内容
        user_content = f"""
        原标题：{row_data.get('title', 'N/A')}
        发布者：{row_data.get('channel_name', 'N/A')}
        字幕/文本内容：{row_data.get('rawtext', 'N/A')[:800]} 
        """
        # (注：截取前800字符避免Token溢出)

        data = {
            "model": API_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.7 
        }

        try:
            response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            content = response.json()["choices"][0]["message"]["content"].strip()
            
            # 清洗可能存在的 Markdown 代码块标记 (```json ... ```)
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            
            result_json = json.loads(content)
            return result_json

        except Exception as e:
            print(f"⚠️ API 调用出错: {e}")
            # 出错返回默认值，不中断程序
            return {"score": 0, "category": "Error", "filename": "API错误", "reason": str(e)}

    def run_curation(self):
        """主执行循环"""
        results = []
        total = len(self.df)
        
        print(f"🚀 开始处理 {total} 条视频...")
        
        for index, row in self.df.iterrows():
            raw_text = str(row['rawtext'])
            
            # 1. 本地敏感词过滤 (省钱)
            is_sensitive, keyword = self.filter.check(raw_text)
            if is_sensitive:
                print(f"[{index+1}/{total}] 🚫 包含敏感词 '{keyword}' -> 跳过")
                continue
            
            # 2. 准备数据
            row_data = {
                'title': row['title'],
                'channel_name': row['channel_name'],
                'rawtext': raw_text
            }
            
            # 3. API 处理
            # 打印进度
            print(f"[{index+1}/{total}] 🤖 正在分析: {row['channel_name']}...", end="", flush=True)
            
            ai_result = self.call_ai_analysis(row_data)
            score = ai_result.get('score', 0)
            
            print(f" -> 评分: {score} | {ai_result.get('filename', '')}")

            # 4. 筛选逻辑 (保留 6 分及以上的视频)
            if score >= 6:
                results.append({
                    '原始ID': index,
                    'B站风格标题': ai_result.get('filename', ''),
                    'AI评分': score,
                    '推荐分类': ai_result.get('category', ''),
                    '推荐理由': ai_result.get('reason', ''),
                    '原始链接': row.get('Video File', ''),
                    '原始播放量': row['viewCount']
                })
                
            # 避免 API 速率限制 (QPS)，稍微 sleep 一下
            time.sleep(0.5)

        # 5. 导出结果
        if results:
            result_df = pd.DataFrame(results)
            # 按评分降序，播放量降序
            result_df = result_df.sort_values(by=['AI评分', '原始播放量'], ascending=[False, False])
            
            result_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
            print(f"\n✅ 筛选完成！已保存 {len(result_df)} 条精选内容至: {OUTPUT_FILE}")
            print("\n🔥 TOP 3 推荐预览：")
            print(result_df[['B站风格标题', 'AI评分']].head(3).to_string(index=False))
        else:
            print("\n⚠️ 没有筛选出符合条件的视频，请检查评分标准或源文件。")

# ==========================================
# 3. 运行程序
# ==========================================
if __name__ == '__main__':
    curator = VideoCurator(INPUT_FILE)
    if curator.load_data():
        curator.run_curation()
import asyncio
import json
import random
import os
import shutil
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ==================== 配置区 ====================
SCRIPT_DIR = Path(__file__).parent
# 确保视频文件夹路径正确（根据你的实际目录调整）
VIDEO_FOLDER = SCRIPT_DIR / "output" / "moved_files"
COOKIE_FILE = SCRIPT_DIR / "cookies" / "douyin_cookies.json"
UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"

CHROME_CONFIG = {
    "user_data_dir": SCRIPT_DIR / "chrome_data" / "douyin",
}

ANTI_DETECT_CONFIG = {
    "min_wait_between_videos": 15,
    "max_wait_between_videos": 35,
    "random_typing_delay": True,
}

# ==================== 路径探测工具 ====================
def get_chrome_path():
    """自动检测系统中 Chrome 的路径"""
    system = platform.system().lower()
    
    # 1. 尝试使用 shutil 自动查找环境变量中的路径
    names = ["google-chrome-stable", "google-chrome", "chromium-browser", "chromium"]
    for name in names:
        path = shutil.which(name)
        if path: return path

    # 2. 常见系统默认路径硬编码检测
    if system == "windows":
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
    elif system == "darwin": # macOS
        paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else: # Linux
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser"
        ]
    
    for p in paths:
        if Path(p).exists(): return p
    return None

# ==================== 调试管理器 ====================
class DebugManager:
    def __init__(self):
        self.debug_dir = SCRIPT_DIR / "debug_douyin"
        self.debug_dir.mkdir(exist_ok=True)

    async def save_failure(self, page, stage, video_path=""):
        timestamp = datetime.now().strftime("%H%M%S")
        day = datetime.now().strftime("%Y-%m-%d")
        v_name = "".join(x for x in Path(video_path).stem if x.isalnum())[:10]
        
        save_path = self.debug_dir / day
        save_path.mkdir(exist_ok=True)
        prefix = f"{timestamp}_{stage}_{v_name}"
        
        try:
            await page.screenshot(path=str(save_path / f"{prefix}.png"), full_page=True)
            source = await page.content()
            with open(save_path / f"{prefix}.html", "w", encoding="utf-8") as f:
                f.write(source)
            print(f"📸 [Debug] 故障现场已保存: {day}/{prefix}.png")
        except Exception as e:
            print(f"⚠️ 调试保存失败: {e}")

debug_mgr = DebugManager()

# ==================== 核心上传函数 ====================
async def upload_single_video(page, context, video_path, title, tags, index, total):
    v_stem = Path(video_path).stem
    print(f"\n🚀 [{index}/{total}] 准备上传: {v_stem}")

    try:
        # 1. 进入页面
        await page.goto(UPLOAD_URL, wait_until="networkidle", timeout=30000)
        
        # 2. 提交文件
        file_input = page.locator("input[type='file']")
        await file_input.wait_for(state="attached", timeout=10000)
        await file_input.set_input_files(video_path)

        # 3. 填写信息
        await page.wait_for_selector(".notranslate", timeout=40000)
        editor = page.locator(".notranslate")
        await editor.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(title)
        
        for tag in tags[:5]:
            await page.keyboard.type(f" #{tag}")
            await asyncio.sleep(1.5) # 必须等联想词
            await page.keyboard.press("Space")
        
        # 4. 等待转码
        print("  正在等待云端转码...")
        await page.get_by_text("重新上传").wait_for(state="visible", timeout=300000)

        # 5. 发布
        publish_btn = page.get_by_role('button', name="发布", exact=True)
        await publish_btn.click()
        
        await page.wait_for_url("**/content/manage**", timeout=20000)
        print("  🎉 发布成功！")
        return True

    except Exception as e:
        await debug_mgr.save_failure(page, "error", video_path)
        print(f"  ❌ [{v_stem}] 失败: {e}")
        return False

# ==================== 执行逻辑 ====================
async def batch_upload(headless=True):
    print("\n" + "="*50)
    print("🎵 抖音批量上传（修正版）启动中...")
    print("="*50)

    # 自动探测 Chrome
    chrome_path = get_chrome_path()
    if not chrome_path:
        print("❌ 未找到 Chrome 浏览器，请检查是否安装。")
        return

    # 扫描视频
    if not VIDEO_FOLDER.exists(): VIDEO_FOLDER.mkdir(parents=True)
    video_files = [str(f) for f in VIDEO_FOLDER.glob("*.mp4")]
    if not video_files:
        print(f"❌ 文件夹 {VIDEO_FOLDER} 中没发现视频")
        return

    async with async_playwright() as p:
        # 启动持久化上下文（模拟真实浏览器环境）
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_CONFIG["user_data_dir"]),
            executable_path=chrome_path,
            headless=headless,
            viewport={'width': 1920, 'height': 1080},
            args=['--no-sandbox', '--disable-setuid-sandbox'] if platform.system() != "Windows" else []
        )

        # 注入 Cookie
        if COOKIE_FILE.exists():
            with open(COOKIE_FILE, 'r') as f:
                storage_state = json.load(f)
                await context.add_cookies(storage_state.get("cookies", []))
            print(f"✅ 已载入 Cookie 记录")
        else:
            print(f"⚠️ 未发现 Cookie 文件: {COOKIE_FILE}, 请先运行获取 Cookie 的脚本")
            await context.close()
            return

        page = context.pages[0]
        success_count = 0
        
        for i, v_path in enumerate(video_files, 1):
            # 基础模拟生成标题
            title = Path(v_path).stem
            tags = ["日常", "记录"]
            
            res = await upload_single_video(page, context, v_path, title, tags, i, len(video_files))
            if res: success_count += 1
            
            if i < len(video_files):
                wait = random.randint(ANTI_DETECT_CONFIG["min_wait_between_videos"], ANTI_DETECT_CONFIG["max_wait_between_videos"])
                print(f"⏳ 等待 {wait} 秒后处理下一个...")
                await asyncio.sleep(wait)

        print(f"\n📊 任务结束: 成功 {success_count} / 总计 {len(video_files)}")
        await context.close()

if __name__ == '__main__':
    asyncio.run(batch_upload(headless=True))
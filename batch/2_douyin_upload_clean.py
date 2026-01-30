import asyncio
import json
import random
import os
import shutil
import platform
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ==================== 配置区 ====================
SCRIPT_DIR = Path(__file__).parent
VIDEO_FOLDER = SCRIPT_DIR / "output" / "moved_files"
COOKIE_FILE = SCRIPT_DIR / "cookies" / "douyin_cookies.json"
UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
# 验证 URL：内容管理页面，只有登录后能访问
CHECK_URL = "https://creator.douyin.com/creator-micro/content/manage"

CHROME_CONFIG = {
    "user_data_dir": SCRIPT_DIR / "chrome_data" / "douyin",
}

ANTI_DETECT_CONFIG = {
    "min_wait_between_videos": 15,
    "max_wait_between_videos": 35,
    "random_typing_delay": True,
}

# ==================== 路径探测与调试工具 ====================
def get_chrome_path():
    system = platform.system().lower()
    names = ["google-chrome-stable", "google-chrome", "chromium-browser", "chromium"]
    for name in names:
        path = shutil.which(name)
        if path: return path
    if system == "windows":
        paths = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    elif system == "darwin":
        paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        paths = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"]
    for p in paths:
        if Path(p).exists(): return p
    return None

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
            with open(save_path / f"{prefix}.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            print(f"📸 [Debug] 现场已保存: {day}/{prefix}.png")
        except Exception as e:
            print(f"⚠️ 调试保存失败: {e}")

debug_mgr = DebugManager()

# ==================== 新增：Cookie 有效性检查 ====================
async def check_cookie_validity(page):
    """
    通过访问管理后台判断 Cookie 是否依然有效
    """
    print("🔍 正在验证 Cookie 有效性...")
    try:
        # 访问管理后台
        await page.goto(CHECK_URL, wait_until="networkidle", timeout=20000)
        await asyncio.sleep(2)
        
        # 逻辑判断：如果当前 URL 包含 'login' 或者不包含 'creator-micro'，说明掉线了
        current_url = page.url
        if "login" in current_url or "creator-micro" not in current_url:
            return False
            
        # 进阶判断：检查页面是否有“发布视频”按钮或头像元素
        # 抖音创作者中心左侧菜单通常有“内容管理”字样
        if await page.get_by_text("内容管理").is_visible():
            return True
            
        return False
    except Exception as e:
        print(f"⚠️ 验证过程发生错误: {e}")
        return False

# ==================== 核心上传逻辑 ====================
async def upload_single_video(page, context, video_path, title, tags, index, total):
    v_stem = Path(video_path).stem
    print(f"\n🚀 [{index}/{total}] 准备上传: {v_stem}")

    try:
        await page.goto(UPLOAD_URL, wait_until="networkidle", timeout=30000)
        
        file_input = page.locator("input[type='file']")
        await file_input.wait_for(state="attached", timeout=10000)
        await file_input.set_input_files(video_path)

        await page.wait_for_selector(".notranslate", timeout=40000)
        editor = page.locator(".notranslate")
        await editor.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(title)
        
        for tag in tags[:5]:
            await page.keyboard.type(f" #{tag}")
            await asyncio.sleep(1.5)
            await page.keyboard.press("Space")
        
        print("  正在等待云端转码...")
        await page.get_by_text("重新上传").wait_for(state="visible", timeout=300000)

        publish_btn = page.get_by_role('button', name="发布", exact=True)
        await publish_btn.click()
        
        await page.wait_for_url("**/content/manage**", timeout=20000)
        print("  🎉 发布成功！")
        return True

    except Exception as e:
        await debug_mgr.save_failure(page, "upload_error", video_path)
        print(f"  ❌ [{v_stem}] 失败: {e}")
        return False

# ==================== 执行逻辑 ====================
async def batch_upload(headless=True):
    print("\n" + "="*50)
    print("🎵 抖音批量上传（增强验证版）启动中...")
    print("="*50)

    chrome_path = get_chrome_path()
    if not chrome_path:
        print("❌ 未找到 Chrome 浏览器。")
        return

    if not VIDEO_FOLDER.exists(): VIDEO_FOLDER.mkdir(parents=True)
    video_files = [str(f) for f in VIDEO_FOLDER.glob("*.mp4")]
    if not video_files:
        print(f"❌ 没发现视频文件。")
        return

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_CONFIG["user_data_dir"]),
            executable_path=chrome_path,
            headless=headless,
            viewport={'width': 1920, 'height': 1080},
            args=['--no-sandbox', '--disable-setuid-sandbox'] if platform.system() != "Windows" else []
        )

        # 1. 加载并注入 Cookie
        if COOKIE_FILE.exists():
            with open(COOKIE_FILE, 'r') as f:
                storage_state = json.load(f)
                # 兼容 storage_state 格式和纯 cookies 列表格式
                cookies = storage_state.get("cookies", []) if isinstance(storage_state, dict) else storage_state
                await context.add_cookies(cookies)
            print(f"✅ 已注入 Cookie 记录")
        else:
            print(f"❌ 未发现 Cookie 文件: {COOKIE_FILE}")
            await context.close()
            return

        page = context.pages[0]
        
        # --- 关键步骤：正式上传前检测有效性 ---
        is_logged_in = await check_cookie_validity(page)
        if not is_logged_in:
            print("\n" + "!"*50)
            print("❌ Cookie 已失效或登录已过期！")
            print("💡 请先运行扫码登录脚本重新获取 Cookies。")
            print("!"*50 + "\n")
            await debug_mgr.save_failure(page, "login_invalid")
            await context.close()
            return

        print("✅ 登录状态验证通过，开始处理上传队列...\n")

        # 2. 循环上传
        success_count = 0
        for i, v_path in enumerate(video_files, 1):
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
    # 第一次运行建议 headless=False 观察一下检测过程
    asyncio.run(batch_upload(headless=True))
"""
腾讯视频号批量上传脚本（生产稳定版）
优化内容：Cookie 校验、Linux 环境适配、失败截图调试
"""
import asyncio
import json
import sys
import random
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# 基础路径配置
SCRIPT_DIR = Path(__file__).parent
VIDEO_FOLDER = Path("output/moved_files")
COOKIE_FILE = SCRIPT_DIR / "cookies" / "weixin_cookies.json"
DEBUG_DIR = SCRIPT_DIR / "debug_screenshots"
DEBUG_DIR.mkdir(exist_ok=True)

# 核心配置
ANTI_DETECT_CONFIG = {
    "min_wait_between_videos": 15,
    "max_wait_between_videos": 35,
    "page_load_timeout": 30000,
    "upload_timeout": 180000, # 3分钟
}

# ==================== 1. 新增：Cookie 有效性检查 ====================
async def verify_cookie_validity(page):
    """验证当前 Cookie 是否依然有效"""
    print("🔍 正在验证 Cookie 有效性...")
    try:
        # 尝试进入视频号后台主页
        await page.goto("https://channels.weixin.qq.com/platform", wait_until="networkidle", timeout=20000)
        await asyncio.sleep(2)
        
        current_url = page.url
        # 如果 URL 包含 login 或者页面出现登录字样，说明 Cookie 失效
        if "login" in current_url.lower():
            print("❌ Cookie 已失效：页面已被重定向至登录页")
            return False
        
        # 检查是否包含创作者中心的关键元素（如：退出登录按钮或头像）
        is_logged_in = await page.locator('span:has-text("退出"), .user-name').count() > 0
        if is_logged_in:
            print("✅ Cookie 验证通过，已登录创作者后台")
            return True
        else:
            print("⚠️ 未能在页面找到登录标识，Cookie 可能已过期")
            await save_debug_screenshot(page, "cookie_check_failed")
            return False
    except Exception as e:
        print(f"❌ 验证 Cookie 时发生异常: {e}")
        return False

# ==================== 2. 增强：Linux 浏览器配置 ====================
def get_browser_args():
    """针对 Linux/Docker 环境优化的启动参数"""
    args = [
        "--no-sandbox",                      # Linux 下 root 用户运行必备
        "--disable-setuid-sandbox",          # 禁用沙盒提升权限
        "--disable-dev-shm-usage",           # 防止 Docker 中 /dev/shm 内存不足导致崩溃
        "--disable-gpu",                     # 无头模式下禁用 GPU 渲染
        "--disable-software-rasterizer",     # 禁用软件光栅化
        "--font-render-hinting=none",        # 优化 Linux 下字体渲染
        "--disable-extensions",              # 禁用插件
        "--mute-audio",                      # 静音
        "--window-size=1920,1080",           # 固定窗口大小
    ]
    return args

# ==================== 3. 辅助功能 (截图与延时) ====================
async def save_debug_screenshot(page, stage_name, video_name=""):
    timestamp = datetime.now().strftime("%H%M%S")
    safe_name = Path(video_name).stem[:15] if video_name else "sys"
    path = DEBUG_DIR / f"{timestamp}_{safe_name}_{stage_name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"📸 [Debug] 截图已存: {path.name}")

async def random_delay(min_s=2, max_s=5):
    await asyncio.sleep(random.uniform(min_s, max_s))

# ==================== 4. 核心上传函数 ====================
async def upload_single_video(page, context, video_path, title, tags, index, total):
    video_name = Path(video_path).name
    print(f"\n🚀 [{index}/{total}] 准备上传: {video_name}")

    try:
        # 进入创作页
        await page.goto("https://channels.weixin.qq.com/platform/post/create", wait_until="networkidle")
        await random_delay()

        # 填写文件
        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(video_path)
        print(f"  > 文件已选择，正在上传...")

        # 填写详情
        editor = page.locator("div.input-editor")
        await editor.click()
        await page.keyboard.type(title)
        for tag in tags[:5]:
            await page.keyboard.type(f" #{tag}")
            await page.keyboard.press("Space")
        
        # 原创声明
        try:
            if await page.locator('div.declare-original-checkbox').is_visible():
                await page.locator('div.declare-original-checkbox').click()
                await page.locator('button:has-text("声明原创")').click()
                print("  > 已勾选原创声明")
        except: pass

        # 等待发表按钮可用
        publish_btn = page.locator('button:has-text("发表")').first
        start_time = time.time()
        while time.time() - start_time < ANTI_DETECT_CONFIG["upload_timeout"] / 1000:
            btn_state = await publish_btn.get_attribute("class") or ""
            if "disabled" not in btn_state.lower():
                break
            await asyncio.sleep(3)
        else:
            raise Exception("上传超时：发表按钮长期不可用")

        # 发表
        await publish_btn.click()
        
        # 结果确认
        for _ in range(10):
            if "post/list" in page.url:
                print(f"✅ 发布成功")
                await context.storage_state(path=str(COOKIE_FILE))
                return True
            await asyncio.sleep(2)
        
        await save_debug_screenshot(page, "publish_unknown_state", video_name)
        return False

    except Exception as e:
        print(f"❌ 上传失败 ({video_name}): {e}")
        await save_debug_screenshot(page, "fail_trace", video_name)
        return False

# ==================== 5. 主程序逻辑 ====================
async def batch_upload(headless=True):
    # 加载 Cookie
    if not COOKIE_FILE.exists():
        print("❌ 错误: Cookie 文件不存在")
        return

    with open(COOKIE_FILE, 'r') as f:
        cookies = json.load(f)
        cookies = cookies["cookies"] if isinstance(cookies, dict) else cookies

    video_files = [str(f) for f in VIDEO_FOLDER.glob("*.mp4")]
    if not video_files:
        print("📁 文件夹内没有 MP4 视频")
        return

    async with async_playwright() as p:
        # 启动针对 Linux 优化的浏览器
        browser = await p.chromium.launch(
            headless=headless,
            args=get_browser_args()
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        # 第一步：先验证 Cookie
        if not await verify_cookie_validity(page):
            print("🛑 请重新获取 Cookie 后运行脚本！")
            await browser.close()
            return

        # 第二步：开始批量上传
        for i, video_path in enumerate(video_files, 1):
            title = Path(video_path).stem
            tags = ["生活", "日常"] # 可根据你的 utils 动态生成
            
            await upload_single_video(page, context, video_path, title, tags, i, len(video_files))
            
            if i < len(video_files):
                wait = random.randint(ANTI_DETECT_CONFIG["min_wait_between_videos"], ANTI_DETECT_CONFIG["max_wait_between_videos"])
                print(f"⏳ 等待 {wait} 秒后处理下一个...")
                await asyncio.sleep(wait)

        await browser.close()
        print("\n🏁 所有任务执行完毕")

if __name__ == "__main__":
    # 在 Linux 服务器上运行时，请确保 headless=True
    asyncio.run(batch_upload(headless=True))
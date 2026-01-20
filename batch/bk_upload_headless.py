import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image

# ==================== 配置区 ====================
import platform
import os

# 自动检测操作系统和浏览器路径
SYSTEM = platform.system()

# 根据操作系统设置默认浏览器路径
if SYSTEM == "Linux":
    # Linux 服务器通常使用系统安装的 chromium
    LOCAL_EXECUTABLE_PATH = '/usr/bin/google-chrome-stable' # 使用系统默认的 chromium
elif SYSTEM == "Darwin":  # macOS
    LOCAL_EXECUTABLE_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
else:  # Windows
    LOCAL_EXECUTABLE_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 可以通过环境变量覆盖浏览器路径
if os.getenv("CHROME_PATH"):
    LOCAL_EXECUTABLE_PATH = os.getenv("CHROME_PATH")

# 文件路径配置
FOLDER_PATH = Path("output/moved_files")
COVER_FOLDER_PATH = Path("output/moved_files")
COOKIES_FILE = Path("tc_cookies.json")

# 无头模式配置（True=无头模式，False=显示浏览器）
#HEADLESS_MODE = os.getenv("HEADLESS", "false").lower() == "true"
HEADLESS_MODE = True #os.getenv("HEADLESS", "false").lower() == "true"

# 封面最小分辨率要求
MIN_COVER_WIDTH = 752
MIN_COVER_HEIGHT = 360

# ==================== 工具函数 ====================
async def human_sleep(min_seconds=1, max_seconds=3):
    """模拟人类操作的随机等待"""
    t = random.uniform(min_seconds, max_seconds)
    print(f"⏳ 等待 {t:.2f} 秒...")
    await asyncio.sleep(t)


def is_valid_image(img_path, min_width=MIN_COVER_WIDTH, min_height=MIN_COVER_HEIGHT):
    """检查图片是否符合分辨率要求"""
    try:
        with Image.open(img_path) as img:
            width, height = img.size
            if width >= min_width and height >= min_height:
                return True
            print(f"⏩ 分辨率不足: {img_path.name} ({width}x{height})")
            return False
    except Exception as e:
        print(f"❌ 无法读取图片 {img_path.name}: {e}")
        return False


def find_cover_for_video(video_path, cover_folder):
    """为视频查找对应的封面文件（png或jpg）"""
    video_name = video_path.stem

    # 尝试查找 png
    cover_path = cover_folder / f"{video_name}.png"
    if cover_path.exists() and is_valid_image(cover_path):
        return cover_path

    # 尝试查找 jpg
    cover_path = cover_folder / f"{video_name}.jpg"
    if cover_path.exists() and is_valid_image(cover_path):
        return cover_path

    return None


# ==================== 上传功能 ====================
async def upload_cover(page, cover_path):
    """上传封面图片"""
    try:
        # 点击上传按钮
        upload_button = page.get_by_role("img", name="plus")
        await upload_button.wait_for(state="visible", timeout=10000)
        await upload_button.click()

        # 上传文件
        cover_input = page.locator("span.ant-upload input[type='file']")
        await cover_input.wait_for(state="attached", timeout=10000)
        await cover_input.set_input_files(str(cover_path))

        return True
    except Exception as e:
        print(f"❌ 上传封面失败: {e}")
        await page.screenshot(path="upload_error.png")
        return False


async def process_cover_crop(page):
    """处理封面裁剪"""
    try:
        await page.get_by_role("dialog", name="裁剪封面").locator("img").click()
        await human_sleep(0.5, 1)
        await page.get_by_text("封面未裁剪").first.click()
        await page.get_by_text("封面未裁剪").click()
        await human_sleep(0.5, 1)
        await page.get_by_role("button", name="完 成").click()
        return True
    except Exception as e:
        print(f"❌ 封面裁剪失败: {e}")
        return False


async def upload_single_video(page, video_path, cover_path):
    """上传单个视频"""
    print(f"\n🚀 准备上传: {video_path.name}")

    try:
        # 打开上传页面
        await page.goto("https://shizi.qq.com/creation/video")
        await page.get_by_role("button", name="本地上传").wait_for(state="visible")
        await human_sleep(2, 4)

        # 上传视频
        video_input = page.locator("input[type='file'][accept^='video']")
        await video_input.wait_for(state="attached")
        await video_input.set_input_files(str(video_path))

        # 等待视频上传成功
        await page.locator("text=视频上传成功").wait_for(state="visible")
        print(f"✅ 视频上传成功: {video_path.name}")
        await human_sleep(1, 2)

        # 上传封面
        if not await upload_cover(page, cover_path):
            return False
        print(f"✅ 封面上传成功: {cover_path.name}")

        # 裁剪封面
        if not await process_cover_crop(page):
            return False
        await human_sleep(1, 2)

        # 声明原创
        await page.get_by_text("声明原创").click()
        await page.get_by_text("该视频非AI生成").click()
        print("✅ 原创声明完成")
        await human_sleep(1, 2)

        # 发布视频
        await page.get_by_role("button", name="发 布").click()
        await human_sleep(0.5, 1)
        await page.get_by_role("button", name="发 布").click()

        print("✅ 发布成功！")
        await human_sleep(3, 6)

        return True

    except Exception as e:
        print(f"❌ 上传失败: {video_path.name}, 错误: {e}")
        return False


# ==================== 主函数 ====================
async def main():
    """主上传流程"""
    # 查找所有视频文件
    videos = list(FOLDER_PATH.glob("*.mp4"))
    if not videos:
        print("😕 找不到任何 mp4 视频文件，请确认目录正确")
        return

    print(f"📊 找到 {len(videos)} 个视频文件")

    # 初始化浏览器
    async with async_playwright() as p:
        # 浏览器启动参数
        launch_options = {
            "headless": HEADLESS_MODE,
        }

        # 只在指定了路径时才添加 executable_path
        if LOCAL_EXECUTABLE_PATH:
            launch_options["executable_path"] = LOCAL_EXECUTABLE_PATH

        # Linux 无头模式需要额外参数
        if SYSTEM == "Linux":
            launch_options["args"] = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]

        print(f"🖥️  系统: {SYSTEM}")
        print(f"🌐 无头模式: {HEADLESS_MODE}")

        browser = await p.chromium.launch(**launch_options)
        context = await browser.new_context()
        context.set_default_timeout(0)

        # 加载 cookies
        if COOKIES_FILE.exists():
            cookies = json.loads(COOKIES_FILE.read_text())
            await context.add_cookies(cookies)
            print("✅ Cookies 加载成功")
        else:
            print("⚠️ cookies.json 不存在，可能需要先登录")

        page = await context.new_page()

        # 上传每个视频
        success_count = 0
        for video_path in videos:
            # 查找对应封面
            cover_path = find_cover_for_video(video_path, COVER_FOLDER_PATH)
            if not cover_path:
                print(f"⚠️ 未找到合适的封面，跳过: {video_path.name}")
                continue

            # 上传视频
            if await upload_single_video(page, video_path, cover_path):
                success_count += 1

        print(f"\n📊 上传完成！成功: {success_count}/{len(videos)}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

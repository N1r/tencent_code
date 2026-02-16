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

import functools
print = functools.partial(print, flush=True)

# 根据操作系统设置默认浏览器路径
if SYSTEM == "Linux":
    # Linux 服务器通常使用系统安装的 chromium
    LOCAL_EXECUTABLE_PATH = None  # 使用系统默认的 chromium
elif SYSTEM == "Darwin":  # macOS
    LOCAL_EXECUTABLE_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
else:  # Windows
    LOCAL_EXECUTABLE_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 可以通过环境变量覆盖浏览器路径
if os.getenv("CHROME_PATH"):
    LOCAL_EXECUTABLE_PATH = os.getenv("CHROME_PATH")
# 文件路径配置
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

# ==================== 工具函数 ====================
async def save_error_screenshot(page, video_name):
    """保存错误截图"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"error_{timestamp}_{video_name}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"📸 已保存错误截图至: {screenshot_path}")
    except Exception as e:
        print(f"⚠️ 无法保存截图: {e}")
        
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


async def validate_cookies(page):
    """验证 cookies 是否有效"""
    try:
        print("🔍 正在验证 cookies 有效性...")
        await page.goto("https://shizi.qq.com/creation/video", wait_until="domcontentloaded")
        await human_sleep(2, 3)

        # 检查是否需要登录（判断页面是否有登录相关元素）
        # 方法1: 检查是否跳转到登录页
        current_url = page.url
        if "login" in current_url or "passport" in current_url:
            print("❌ Cookies 已失效，需要重新登录")
            return False

        # 方法2: 检查是否能找到上传按钮（说明已登录）
        try:
            await page.get_by_role("button", name="本地上传").wait_for(state="visible", timeout=5000)
            print("✅ Cookies 有效，已登录")
            return True
        except:
            print("❌ Cookies 可能已失效，未找到上传按钮")
            return False

    except Exception as e:
        print(f"⚠️ 验证 cookies 时出错: {e}")
        return False


async def upload_single_video(context, video_path, cover_path):
    """上传单个视频（每次创建新页面避免内存累积）"""
    print(f"\n🚀 准备上传: {video_path.name}")

    # 每次上传创建新页面，避免内存累积
    page = await context.new_page()

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

    finally:
        # 关闭页面释放内存
        try:
            await page.close()
        except:
            pass


# ==================== 浏览器管理 ====================
def get_launch_options():
    """获取浏览器启动参数"""
    launch_options = {
        "headless": HEADLESS_MODE,
    }

    if LOCAL_EXECUTABLE_PATH:
        launch_options["executable_path"] = LOCAL_EXECUTABLE_PATH

    # Linux 无头模式需要额外参数（内存优化）
    if SYSTEM == "Linux":
        launch_options["args"] = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            # 内存优化参数
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--mute-audio",
            "--no-first-run",
            "--safebrowsing-disable-auto-update",
            "--js-flags=--max-old-space-size=512",
        ]

    return launch_options


async def create_browser_context(p, cookies):
    """创建浏览器和上下文"""
    launch_options = get_launch_options()
    browser = await p.chromium.launch(**launch_options)
    context = await browser.new_context()
    context.set_default_timeout(0)

    if cookies:
        await context.add_cookies(cookies)

    return browser, context


# ==================== 主函数 ====================
async def main():
    """主上传流程"""
    # 查找所有视频文件
    videos = list(FOLDER_PATH.glob("*.mp4"))
    if not videos:
        print("😕 找不到任何 mp4 视频文件，请确认目录正确")
        return

    print(f"📊 找到 {len(videos)} 个视频文件")
    print(f"🖥️  系统: {SYSTEM}")
    print(f"🌐 无头模式: {HEADLESS_MODE}")

    # 加载 cookies
    cookies = None
    if COOKIES_FILE.exists():
        cookies = json.loads(COOKIES_FILE.read_text())
        print("✅ Cookies 加载成功")
    else:
        print("⚠️ cookies.txt 不存在，可能需要先登录")
        return

    async with async_playwright() as p:
        browser, context = await create_browser_context(p, cookies)

        # 验证 cookies 有效性
        test_page = await context.new_page()
        if not await validate_cookies(test_page):
            print("\n❌ Cookies 验证失败，请先运行登录脚本获取有效的 cookies")
            await browser.close()
            return
        await test_page.close()

        # 上传每个视频
        success_count = 0
        for i, video_path in enumerate(videos):
            # 查找对应封面
            cover_path = find_cover_for_video(video_path, COVER_FOLDER_PATH)
            if not cover_path:
                print(f"⚠️ 未找到合适的封面，跳过: {video_path.name}")
                continue

            # 尝试上传，如果浏览器崩溃则重启
            max_retries = 2
            for retry in range(max_retries):
                try:
                    if await upload_single_video(context, video_path, cover_path):
                        success_count += 1
                    break
                except Exception as e:
                    if "closed" in str(e).lower() or "crashed" in str(e).lower():
                        print(f"🔄 浏览器崩溃，正在重启... (重试 {retry + 1}/{max_retries})")
                        try:
                            await browser.close()
                        except:
                            pass
                        await asyncio.sleep(3)
                        browser, context = await create_browser_context(p, cookies)
                    else:
                        print(f"❌ 上传出错: {e}")
                        break

            # 每上传一个视频后，等待一下让系统回收内存
            if i < len(videos) - 1:
                print("⏳ 等待系统回收内存...")
                await asyncio.sleep(5)

        print(f"\n📊 上传完成！成功: {success_count}/{len(videos)}")
        try:
            await browser.close()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())

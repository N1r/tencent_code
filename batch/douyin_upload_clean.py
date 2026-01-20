"""
抖音视频批量上传脚本（精简版）
使用 Playwright 和 cookies 自动登录上传
支持单实例批量上传，添加防风控机制
"""
import asyncio
import json
import sys
import random
from pathlib import Path
from playwright.async_api import async_playwright

# 添加父目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ut_upload import find_mp4_files, generate_title_and_tags
except ImportError:
    print("❌ 导入错误: 找不到 utils 模块")
    sys.exit(1)

# 获取基础目录
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent

# ==================== 配置区 ====================
# 视频文件夹路径
VIDEO_FOLDER = Path("output/moved_files")

# Cookie 文件路径
COOKIE_FILE = SCRIPT_DIR / "cookies" / "douyin_cookies.json"

# 抖音上传页面
UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"

# 本地Chrome配置
CHROME_CONFIG = {
    "auto_detect": True,  # 自动检测Chrome路径
    "custom_path": None,  # 自定义Chrome路径，如果auto_detect为False则使用此路径
    "user_data_dir": SCRIPT_DIR / "chrome_data" / "douyin",  # 用户数据目录
    "profile_name": "douyin_profile"  # 配置文件名
}

# 防风控配置 - 优化Linux无头模式
ANTI_DETECT_CONFIG = {
    "min_wait_between_videos": 15,  # 视频间最小等待时间（秒）- 减少间隔
    "max_wait_between_videos": 35,  # 视频间最大等待时间（秒）- 减少间隔
    "random_mouse_move": True,      # 随机鼠标移动
    "random_typing_delay": True,    # 随机打字延迟
    "page_load_timeout": 15000,     # 页面加载超时（毫秒）
    "element_wait_timeout": 10000,  # 元素等待超时（毫秒）
    "upload_check_interval": 2,     # 上传状态检查间隔（秒）
}


# ==================== Chrome检测和配置 ====================
def find_chrome_path():
    """自动检测Chrome浏览器路径"""
    import platform
    import subprocess

    system = platform.system().lower()

    # 常见的Chrome路径
    chrome_paths = {
        "windows": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\Application\chrome.exe"
        ],
        "darwin": [  # macOS
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/usr/local/bin/chromium-browser"
        ],
        "linux": [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/opt/google/chrome/chrome"
        ]
    }

    paths_to_check = chrome_paths.get(system, [])

    for path in paths_to_check:
        if Path(path).exists():
            return path

    # 尝试通过命令行查找
    try:
        if system == "windows":
            result = subprocess.run(["where", "chrome"], capture_output=True, text=True)
        else:
            result = subprocess.run(["which", "google-chrome"], capture_output=True, text=True)

        if result.returncode == 0:
            path = result.stdout.strip()
            if Path(path).exists():
                return path
    except:
        pass

    return None


def get_chrome_path():
    """获取Chrome路径"""
    if not CHROME_CONFIG["auto_detect"] and CHROME_CONFIG["custom_path"]:
        return CHROME_CONFIG["custom_path"]

    chrome_path = find_chrome_path()
    if not chrome_path:
        print("❌ 未找到Chrome浏览器，请手动指定路径")
        print("💡 请在CHROME_CONFIG中设置custom_path，或确保Chrome已正确安装")
        return None

    print(f"✅ 找到Chrome: {chrome_path}")
    return chrome_path


# ==================== 防风控工具函数 ====================
async def random_delay(min_seconds=1, max_seconds=3):
    """随机延迟"""
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


async def random_mouse_movement(page):
    """随机鼠标移动"""
    if ANTI_DETECT_CONFIG["random_mouse_move"]:
        x = random.randint(100, 800)
        y = random.randint(100, 600)
        await page.mouse.move(x, y)
        await random_delay(0.2, 0.5)


# ==================== 核心功能 ====================
async def load_cookies():
    """加载 cookies"""
    if not COOKIE_FILE.exists():
        print(f"\n❌ Cookie 文件不存在: {COOKIE_FILE}")
        print("💡 请先运行 get_cookies.py 获取抖音 Cookie")
        return None

    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookies_data = json.load(f)

        # 处理不同格式的cookies数据
        if isinstance(cookies_data, list):
            # 直接是cookies数组
            cookies = cookies_data
        elif isinstance(cookies_data, dict) and "cookies" in cookies_data:
            # 包含cookies字段的对象格式
            cookies = cookies_data["cookies"]
        else:
            print(f"\n❌ Cookie 文件格式不支持: {COOKIE_FILE}")
            return None

        # 确保返回的是数组格式
        if not isinstance(cookies, list):
            print(f"\n❌ Cookie 数据不是数组格式: {COOKIE_FILE}")
            return None

        print(f"✅ 成功加载 {len(cookies)} 个 Cookie")
        return cookies

    except json.JSONDecodeError:
        print(f"\n❌ Cookie 文件格式错误: {COOKIE_FILE}")
        return None
    except Exception as e:
        print(f"\n❌ 加载 Cookie 时发生错误: {e}")
        return None


async def upload_single_video(page, context, video_path, title, tags, index, total):
    """在已有页面上传单个视频"""

    print(f"\n{'='*50}")
    print(f"[{index}/{total}] 上传视频: {Path(video_path).name}")
    print(f"标题: {title}")
    print(f"标签: {', '.join(tags[:3])}")
    print(f"{'='*50}")

    try:
        # 1. 打开上传页面
        print("\n步骤 1: 打开上传页面...")
        await page.goto(UPLOAD_URL)
        await page.wait_for_url(UPLOAD_URL, timeout=10000)
        await random_delay(1, 2)
        print("✅ 页面加载完成")

        # 2. 随机鼠标移动
        await random_mouse_movement(page)

        # 3. 上传视频文件
        print("\n步骤 2: 选择视频文件...")
        file_input = page.locator("div[class^='container'] input")
        await file_input.set_input_files(video_path)
        await random_delay(1, 2)
        print("✅ 视频文件已选择")

        # 4. 等待跳转到发布页
        print("\n步骤 3: 等待视频上传...")
        max_retries = 60
        for i in range(max_retries):
            try:
                await page.wait_for_url("**/content/publish?enter_from=publish_page", timeout=2000)
                print("✅ 进入发布页面（v1）")
                break
            except:
                try:
                    await page.wait_for_url("**/content/post/video?enter_from=publish_page", timeout=2000)
                    print("✅ 进入发布页面（v2）")
                    break
                except:
                    if i % 5 == 0:
                        print(f"  等待中... ({i+1}/{max_retries})")
                        # 偶尔移动鼠标
                        if i % 15 == 0:
                            await random_mouse_movement(page)
                    await asyncio.sleep(2)
        else:
            raise Exception("等待发布页面超时")

        await random_delay(1, 2)

        # 5. 填写标题和标签（模拟人类打字）
        print("\n步骤 4: 填写标题和标签...")

        # 填写标题
        title_input = page.get_by_text('作品标题').locator("..").locator("xpath=following-sibling::div[1]").locator("input")
        if await title_input.count():
            await title_input.click()
            await random_delay(0.3, 0.6)

            # 模拟人类打字
            for char in title[:30]:
                await page.keyboard.type(char)
                if ANTI_DETECT_CONFIG["random_typing_delay"]:
                    await asyncio.sleep(random.uniform(0.05, 0.15))
        else:
            await page.locator(".notranslate").click()
            await random_delay(0.2, 0.5)
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")

            for char in title:
                await page.keyboard.type(char)
                if ANTI_DETECT_CONFIG["random_typing_delay"]:
                    await asyncio.sleep(random.uniform(0.05, 0.15))

        await random_delay(0.5, 1)

        # 填写标签
        for tag in tags[:5]:
            await page.type(".zone-container", "#" + tag)
            if ANTI_DETECT_CONFIG["random_typing_delay"]:
                await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.press(".zone-container", "Space")
            await random_delay(0.3, 0.6)

        print(f"✅ 已填写标题和 {len(tags[:5])} 个标签")

        # 6. 随机鼠标移动
        await random_mouse_movement(page)

        # 7. 等待视频处理完成
        print("\n步骤 5: 等待视频处理完成...")
        max_wait = 300  # 最多等待5分钟
        for i in range(max_wait):
            if await page.locator('[class^="long-card"] div:has-text("重新上传")').count():
                print("✅ 视频处理完成")
                break
            elif await page.locator('div.progress-div > div:has-text("上传失败")').count():
                print("❌ 视频上传失败")
                return False
            else:
                if i % 10 == 0:
                    print(f"  处理中... ({i}/{max_wait}秒)")
                    # 偶尔移动鼠标
                    if i % 30 == 0:
                        await random_mouse_movement(page)
                await asyncio.sleep(1)
        else:
            raise Exception("视频处理超时")

        # 8. 发布前随机延迟
        await random_delay(1, 3)

        # 9. 发布视频
        print("\n步骤 6: 发布视频...")
        publish_button = page.get_by_role('button', name="发布", exact=True)
        if await publish_button.count():
            await publish_button.click()
            await random_delay(0.5, 1)
            print("✅ 点击发布按钮")

        # 等待发布成功
        for i in range(30):
            try:
                await page.wait_for_url("**/content/manage**", timeout=2000)
                print("✅ 视频发布成功！")

                # 保存更新后的 cookies
                await context.storage_state(path=str(COOKIE_FILE))
                print("✅ Cookie 已更新并保存\n")
                return True
            except:
                print(f"  发布中... ({i+1}/30)")
                await asyncio.sleep(1)

        raise Exception("发布超时")

    except Exception as e:
        print(f"\n❌ 上传失败: {e}\n")
        return False


async def batch_upload(headless=False):
    """批量上传视频（单实例）"""

    print("\n" + "="*50)
    print("🎵 抖音批量上传工具（防风控版）")
    print("="*50)

    # 1. 加载 cookies
    cookies = await load_cookies()
    if not cookies:
        return False

    print(f"\n✅ 成功加载 {len(cookies)} 个 Cookie")

    # 2. 扫描视频文件
    print(f"\n📁 视频文件夹: {VIDEO_FOLDER}")
    video_files = find_mp4_files(str(VIDEO_FOLDER), sort_by_date=True, reverse=True)

    if not video_files:
        print("❌ 未找到任何 MP4 文件")
        return False

    print(f"✅ 找到 {len(video_files)} 个视频文件\n")

    # 显示视频列表
    print("视频列表:")
    for index, file_path in enumerate(video_files, 1):
        file_name = Path(file_path).name
        print(f"  {index}. {file_name}")

    # 3. 启动浏览器（单实例）
    print(f"\n🚀 正在启动本地Chrome...")

    # 获取Chrome路径
    chrome_path = get_chrome_path()
    if not chrome_path:
        return False

    # 创建用户数据目录
    user_data_dir = CHROME_CONFIG["user_data_dir"]
    user_data_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        try:
            # 使用本地Chrome启动的参数（不包含user-data-dir）
            browser_args = [
                '--disable-web-security',                        # 禁用网络安全限制
                '--disable-features=IsolateOrigins,site-per-process',  # 禁用站点隔离
                '--no-first-run',                                # 跳过首次运行设置
                '--no-default-browser-check',                    # 跳过默认浏览器检查
                '--disable-background-timer-throttling',         # 禁用后台定时器限制
                '--disable-backgrounding-occluded-windows',      # 禁用窗口遮挡检测
                '--disable-renderer-backgrounding',              # 禁用渲染器后台处理
                '--disable-infobars',                            # 禁用信息栏
                '--window-size=1920,1080',                       # 设置窗口大小
                '--lang=zh-CN',                                  # 设置语言
                '--disable-extensions-except=/dev/null',         # 禁用扩展
                '--disable-plugins',                             # 禁用插件
                '--disable-print-preview',                       # 禁用打印预览
                '--disable-component-extensions-with-background-pages',  # 禁用后台组件
                '--no-service-autorun',                          # 禁用服务自动运行
                '--password-store=basic',                        # 使用基本密码存储
                '--use-mock-keychain',                           # 使用模拟钥匙串
                '--disable-ipc-flooding-protection',             # 禁用IPC洪水保护
            ]

            # 无头模式额外参数
            if headless:
                browser_args.extend([
                    '--disable-gpu',                             # 禁用GPU
                    '--disable-software-rasterizer',             # 禁用软件光栅化
                    '--disable-dev-tools',                       # 禁用开发者工具
                    '--disable-extensions',                      # 完全禁用扩展
                    '--disable-background-networking',           # 禁用后台网络
                ])

            # 使用launch_persistent_context启动（适用于本地Chrome）
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=headless,
                executable_path=chrome_path,
                args=browser_args,
                # 设置上下文参数
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                permissions=['geolocation', 'notifications'],
                color_scheme='light',
                extra_http_headers={
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
                device_scale_factor=1.0,
                is_mobile=False,
                has_touch=False,
            )

            # 注入 cookies
            await context.add_cookies(cookies)

            # 获取页面
            page = context.pages[0] if context.pages else await context.new_page()

            # 注入简化的反检测脚本（使用本地Chrome）
            await page.add_init_script("""
                // 仅隐藏 webdriver 标识，使用本地Chrome时其他属性都是真实的
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // 移除自动化检测相关的全局变量
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_JSON;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Object;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Proxy;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Window;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_XMLHttpRequest;
            """)

            print("✅ 浏览器已启动\n")

            # 4. 开始上传
            print(f"开始批量上传...")
            success_count = 0
            failed_count = 0

            for index, video_path in enumerate(video_files, 1):
                print(f"\n{'='*60}")
                print(f"正在处理第 {index}/{len(video_files)} 个视频")
                print(f"{'='*60}")

                try:
                    # 生成标题和标签
                    title, tags = generate_title_and_tags(video_path, platform="douyin")

                    # 上传视频
                    success = await upload_single_video(page, context, video_path, title, tags, index, len(video_files))

                    if success:
                        success_count += 1
                        print(f"✅ [{index}/{len(video_files)}] 上传成功")
                    else:
                        failed_count += 1
                        print(f"❌ [{index}/{len(video_files)}] 上传失败")

                        # 连续失败3次则停止
                        if failed_count >= 3:
                            print("\n⚠️  连续失败次数过多，停止上传")
                            break

                    # 视频间随机等待（防风控）
                    if index < len(video_files):
                        wait_time = random.randint(
                            ANTI_DETECT_CONFIG["min_wait_between_videos"],
                            ANTI_DETECT_CONFIG["max_wait_between_videos"]
                        )
                        print(f"\n⏳ 等待 {wait_time} 秒后继续（防风控）...")

                        # 分段显示等待进度
                        for i in range(wait_time):
                            if i % 10 == 0:
                                print(f"  剩余 {wait_time - i} 秒...")
                            await asyncio.sleep(1)

                        # 等待期间随机移动鼠标
                        await random_mouse_movement(page)

                except Exception as e:
                    failed_count += 1
                    print(f"❌ [{index}/{len(video_files)}] 发生错误: {e}")

            # 5. 显示统计结果
            print("\n" + "="*50)
            print("📊 上传统计")
            print("="*50)
            print(f"总视频数: {len(video_files)}")
            print(f"成功上传: {success_count}")
            print(f"上传失败: {failed_count}")
            if len(video_files) > 0:
                print(f"成功率: {success_count/len(video_files)*100:.1f}%")
            print("="*50 + "\n")

            # 关闭浏览器上下文
            await context.close()
            print("✅ 浏览器已关闭\n")

            return success_count > 0

        except Exception as e:
            print(f"\n❌ 批量上传失败: {e}\n")
            return False


async def test_single_upload(headless=False):
    """测试上传单个视频"""

    print("\n" + "="*50)
    print("🎵 测试上传单个视频")
    print("="*50)

    # 加载 cookies
    cookies = await load_cookies()
    if not cookies:
        return False

    print(f"\n✅ 成功加载 {len(cookies)} 个 Cookie")

    # 获取第一个视频
    video_files = find_mp4_files(str(VIDEO_FOLDER))
    if not video_files:
        print("❌ 未找到视频文件")
        return False

    video_path = video_files[0]
    print(f"\n📁 测试视频: {Path(video_path).name}")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                locale='zh-CN',
            )
            await context.add_cookies(cookies)
            page = await context.new_page()

            # 注入简化的反检测脚本（使用本地Chrome）
            await page.add_init_script("""
                // 仅隐藏 webdriver 标识，使用本地Chrome时其他属性都是真实的
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // 移除自动化检测相关的全局变量
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_JSON;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Object;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Proxy;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Window;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_XMLHttpRequest;
            """)

            # 生成标题和标签
            title, tags = generate_title_and_tags(video_path, platform="douyin")

            # 上传视频
            success = await upload_single_video(page, context, video_path, title, tags, 1, 1)

            await browser.close()
            return success

        except Exception as e:
            print(f"\n❌ 测试失败: {e}\n")
            return False


# ==================== 主入口 ====================
# def main():
#     """主函数"""
#     print("\n抖音视频上传工具（防风控版）")
#     print("1 - 上传单个视频（测试）")
#     print("2 - 批量上传所有视频（单实例）")

#     try:
#         choice = input("\n请选择操作 [1/2] (默认: 1): ").strip() or "1"

#         # 询问是否使用无头模式
#         headless_choice = input("是否使用无头模式 [y/n] (默认: n): ").strip().lower() or "n"
#         headless = headless_choice == "y"

#         if headless:
#             print("💡 使用无头模式运行")
#         else:
#             print("💡 将打开浏览器窗口")

#         if choice == "1":
#             asyncio.run(test_single_upload(headless))
#         elif choice == "2":
#             asyncio.run(batch_upload(headless))
#         else:
#             print("❌ 无效的选择")

#     except KeyboardInterrupt:
#         print("\n\n⚠️  操作被取消\n")
#     except Exception as e:
#         print(f"\n💥 程序异常: {e}\n")

def main():
    """主函数（无交互，默认批量 + 无头）"""
    print("\n抖音视频上传工具(防风控版)")
    print("💡 默认模式：批量上传 + 无头浏览器")

    try:
        headless = True  # 固定无头模式
        asyncio.run(batch_upload(headless))

    except KeyboardInterrupt:
        print("\n\n⚠️  操作被取消\n")
    except Exception as e:
        print(f"\n💥 程序异常: {e}\n")


if __name__ == '__main__':
    main()

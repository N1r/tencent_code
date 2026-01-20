"""
腾讯视频号批量上传脚本（精简版）
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
COOKIE_FILE = SCRIPT_DIR / "cookies" / "weixin_cookies.json"

# 微信视频号上传页面
UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"

# 本地Chrome配置
CHROME_CONFIG = {
    "auto_detect": True,  # 自动检测Chrome路径
    "custom_path": None,  # 自定义Chrome路径，如果auto_detect为False则使用此路径
    "user_data_dir": SCRIPT_DIR / "chrome_data" / "tencent",  # 基础用户数据目录
    "profile_name": "tencent_profile"  # 配置文件名
}

# 防风控配置 - 优化Linux无头模式
ANTI_DETECT_CONFIG = {
    "min_wait_between_videos": 10,  # 视频间最小等待时间（秒）- 减少间隔
    "max_wait_between_videos": 25,  # 视频间最大等待时间（秒）- 减少间隔
    "random_mouse_move": True,      # 随机鼠标移动
    "random_typing_delay": True,    # 随机打字延迟
    "page_load_timeout": 15000,     # 页面加载超时（毫秒）
    "element_wait_timeout": 10000,  # 元素等待超时（毫秒）
    "upload_check_interval": 2,     # 上传状态检查间隔（秒）
    "headless_extra_wait": True,    # 无头模式额外等待
    "headless_upload_timeout": 60000,  # 无头模式文件上传超时（毫秒）
}

# 视频设置
VIDEO_CONFIG = {
    "enable_original": True,        # 是否声明原创
    "original_category": "生活",    # 原创类型：生活、科技、时尚、美食、旅行、音乐、运动、游戏、教育等
    "enable_collection": True,      # 是否添加到合集
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


def get_unique_user_data_dir(base_dir):
    """生成唯一的用户数据目录，避免配置文件冲突"""
    import uuid
    import time

    # 生成基于时间戳和UUID的唯一目录名
    unique_id = f"{int(time.time())}_{str(uuid.uuid4())[:8]}"
    unique_dir = base_dir.parent / f"{base_dir.name}_{unique_id}"

    # 确保目录存在
    unique_dir.mkdir(parents=True, exist_ok=True)

    print(f"📁 使用唯一用户数据目录: {unique_dir}")
    return unique_dir


# ==================== 防风控工具函数 ====================
async def random_delay(min_seconds=1, max_seconds=3):
    """随机延迟"""
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


async def human_like_type(page, selector, text):
    """模拟人类打字"""
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char)
        if ANTI_DETECT_CONFIG["random_typing_delay"]:
            await asyncio.sleep(random.uniform(0.05, 0.15))


async def random_mouse_movement(page):
    """随机鼠标移动"""
    if ANTI_DETECT_CONFIG["random_mouse_move"]:
        x = random.randint(100, 800)
        y = random.randint(100, 600)
        await page.mouse.move(x, y)
        await random_delay(0.2, 0.5)


async def wait_for_upload_element(page, selector, headless=False, timeout=None):
    """智能等待上传元素出现，针对无头模式优化"""
    if timeout is None:
        if headless and ANTI_DETECT_CONFIG.get("headless_extra_wait", False):
            timeout = ANTI_DETECT_CONFIG.get("headless_upload_timeout", 30000)
        else:
            timeout = ANTI_DETECT_CONFIG.get("element_wait_timeout", 10000)

    # 在无头模式下，增加额外的等待时间
    if headless:
        await page.wait_for_load_state('networkidle', timeout=5000)
        await random_delay(0.5, 1)

    element = page.locator(selector).first
    await element.wait_for(state='attached', timeout=timeout)
    return element


async def add_collection(page):
    """添加到合集"""
    if not VIDEO_CONFIG["enable_collection"]:
        return

    try:
        collection_elements = page.get_by_text("添加到合集").locator("xpath=following-sibling::div").locator('.option-list-wrap > div')
        if await collection_elements.count() > 1:
            await page.get_by_text("添加到合集").locator("xpath=following-sibling::div").click()
            await random_delay(0.3, 0.6)
            await collection_elements.first.click()
            await random_delay(0.3, 0.6)
            print("✅ 已添加到合集")
    except Exception as e:
        print(f"⚠️  添加合集失败（可能不支持）: {e}")


async def add_original(page):
    """添加原创声明"""
    if not VIDEO_CONFIG["enable_original"]:
        return

    try:
        # 方法1: 简单的原创勾选框
        if await page.get_by_label("视频为原创").count():
            await page.get_by_label("视频为原创").check()
            await random_delay(0.5, 1)
            print("✅ 已声明原创（方法1）")

        # 方法2: 需要同意条款的原创声明
        label_locator = await page.locator('label:has-text("我已阅读并同意 《视频号原创声明使用条款》")').is_visible()
        if label_locator:
            await page.get_by_label("我已阅读并同意 《视频号原创声明使用条款》").check()
            await random_delay(0.3, 0.6)
            await page.get_by_role("button", name="声明原创").click()
            await random_delay(0.5, 1)
            print("✅ 已声明原创（方法2）")

        # 方法3: 新版UI，需要选择原创类型
        if await page.locator('div.label span:has-text("声明原创")').count() and VIDEO_CONFIG["original_category"]:
            # 检查原创勾选框是否可用（账号可能因处罚无法勾选）
            if not await page.locator('div.declare-original-checkbox input.ant-checkbox-input').is_disabled():
                await page.locator('div.declare-original-checkbox input.ant-checkbox-input').click()
                await random_delay(0.3, 0.6)

                # 勾选同意条款
                if not await page.locator('div.declare-original-dialog label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible').count():
                    await page.locator('div.declare-original-dialog input.ant-checkbox-input:visible').click()
                    await random_delay(0.3, 0.6)

            # 选择原创类型
            if await page.locator('div.original-type-form > div.form-label:has-text("原创类型"):visible').count():
                await page.locator('div.form-content:visible').click()
                await random_delay(0.3, 0.6)

                # 选择指定分类
                category = VIDEO_CONFIG["original_category"]
                await page.locator(f'div.form-content:visible ul.weui-desktop-dropdown__list li.weui-desktop-dropdown__list-ele:has-text("{category}")').first.click()
                await random_delay(0.5, 1)

            # 点击声明原创按钮
            if await page.locator('button:has-text("声明原创"):visible').count():
                await page.locator('button:has-text("声明原创"):visible').click()
                await random_delay(0.5, 1)
                print(f"✅ 已声明原创（方法3 - {category}）")

    except Exception as e:
        print(f"⚠️  原创声明失败（可能不支持）: {e}")


# ==================== 核心功能 ====================
async def load_cookies():
    """加载 cookies"""
    if not COOKIE_FILE.exists():
        print(f"\n❌ Cookie 文件不存在: {COOKIE_FILE}")
        print("💡 请先运行 get_cookies.py 获取微信视频号 Cookie")
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


async def upload_single_video(page, context, video_path, title, tags, index, total, headless=False):
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

        # 在无头模式下，需要更充分的等待
        if headless:
            print("    📱 无头模式：等待页面组件加载...")
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            await page.wait_for_load_state('networkidle', timeout=15000)

            # 检查页面是否正确加载
            try:
                page_title = await page.title()
                print(f"    📄 页面标题: {page_title}")

                # 检查是否有错误信息
                error_selectors = [
                    '.error-message',
                    '[class*="error"]',
                    'text=/错误|失败|无法/',
                ]
                for selector in error_selectors:
                    if await page.locator(selector).count() > 0:
                        error_text = await page.locator(selector).first.inner_text()
                        print(f"    ⚠️ 检测到页面错误: {error_text}")

            except Exception as e:
                print(f"    ⚠️ 页面状态检查失败: {e}")

        await random_delay(2, 3)  # 增加等待时间
        print("✅ 页面加载完成")

        # 2. 随机鼠标移动（模拟人类行为）
        await random_mouse_movement(page)

        # 3. 上传视频文件
        print("\n步骤 2: 选择视频文件...")

        # 在无头模式下，可能需要更长的等待时间和更稳定的元素定位
        max_retries = 5  # 增加重试次数
        upload_success = False

        for attempt in range(max_retries):
            try:
                print(f"  尝试 {attempt + 1}/{max_retries}...")

                # 在无头模式下，添加额外的等待和调试
                if headless:
                    print("    📸 无头模式：等待页面完全渲染...")
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                    await page.wait_for_load_state('networkidle', timeout=10000)

                    # 截图用于调试（可选）
                    try:
                        await page.screenshot(path=f"debug_upload_{attempt}.png")
                        print(f"    📸 已保存调试截图: debug_upload_{attempt}.png")
                    except:
                        pass

                # 多种定位策略
                file_input = None
                strategies = [
                    # 策略1: 直接定位input[type="file"]
                    'input[type="file"]',
                    # 策略2: 通过class或其他属性定位
                    '.upload-input[type="file"]',
                    'input[accept*="video"]',
                    'input[accept*="mp4"]',
                    # 策略3: 通过父元素定位
                    'div.upload-area input[type="file"]',
                    'div.upload-container input[type="file"]',
                    '.file-input[type="file"]',
                ]

                for strategy in strategies:
                    try:
                        print(f"    🔍 尝试定位策略: {strategy}")
                        file_input = await wait_for_upload_element(
                            page,
                            strategy,
                            headless=headless
                        )
                        if file_input:
                            print(f"    ✅ 找到文件输入元素: {strategy}")
                            break
                    except:
                        continue

                # 如果还没找到，尝试点击上传区域激活
                if not file_input:
                    print("    🎯 尝试激活上传区域...")

                    # 首先列出页面上的所有input元素用于调试
                    try:
                        all_inputs = await page.query_selector_all('input')
                        input_info = []
                        for i, inp in enumerate(all_inputs):
                            try:
                                input_type = await inp.get_attribute('type') or 'text'
                                input_class = await inp.get_attribute('class') or ''
                                input_id = await inp.get_attribute('id') or ''
                                input_info.append(f"{i+1}. type={input_type}, class={input_class}, id={input_id}")
                            except:
                                input_info.append(f"{i+1}. 无法获取属性")

                        if input_info:
                            print(f"    📋 页面上的input元素 ({len(input_info)}个):")
                            for info in input_info[:10]:  # 只显示前10个
                                print(f"       {info}")
                            if len(input_info) > 10:
                                print(f"       ...还有{len(input_info)-10}个")
                    except Exception as e:
                        print(f"    ⚠️ 无法枚举input元素: {e}")

                    upload_triggers = [
                        'div.upload-area',
                        '.upload-container',
                        '[data-testid*="upload"]',
                        'button:has-text("上传")',
                        '.upload-trigger',
                        'div:has-text("点击上传")',
                        'div:has-text("选择文件")',
                        'div:has-text("上传视频")',
                        '.upload-btn',
                        '[role="button"]:has-text("上传")',
                    ]

                    for trigger in upload_triggers:
                        try:
                            trigger_element = page.locator(trigger).first
                            if await trigger_element.count() > 0:
                                print(f"    🎯 尝试点击: {trigger}")
                                await trigger_element.click()
                                await random_delay(1, 2)

                                # 再次尝试定位文件输入
                                file_input = await wait_for_upload_element(
                                    page,
                                    'input[type="file"]',
                                    headless=headless
                                )
                                if file_input:
                                    print("    ✅ 点击后找到文件输入元素")
                                    break
                        except Exception as e:
                            print(f"    ⚠️ 点击 {trigger} 失败: {e}")
                            continue

                if not file_input:
                    print("    ❌ 未找到文件输入元素，尝试下一个策略")

                    # 最后的备选策略：通过JavaScript创建文件输入
                    if attempt == max_retries - 1:  # 最后一次尝试
                        print("    🔧 尝试通过JavaScript创建文件输入...")
                        try:
                            # 创建一个隐藏的文件输入元素
                            await page.evaluate("""
                                const input = document.createElement('input');
                                input.type = 'file';
                                input.accept = 'video/*,.mp4,.mov,.avi';
                                input.style.display = 'none';
                                input.id = 'playwright-file-input';
                                document.body.appendChild(input);
                            """)

                            # 等待元素创建
                            await random_delay(0.5, 1)

                            # 尝试定位新创建的元素
                            file_input = await wait_for_upload_element(
                                page,
                                '#playwright-file-input',
                                headless=headless
                            )

                            if file_input:
                                print("    ✅ 通过JavaScript创建了文件输入元素")

                        except Exception as e:
                            print(f"    ⚠️ JavaScript创建失败: {e}")

                    if not file_input:
                        continue

                # 设置文件，增加超时时间
                print(f"    📁 设置文件: {Path(video_path).name}")
                await file_input.set_input_files(video_path, timeout=ANTI_DETECT_CONFIG["headless_upload_timeout"])
                upload_success = True
                print("✅ 视频文件已选择")
                break

            except Exception as e:
                print(f"  ⚠️  第 {attempt + 1} 次尝试失败: {str(e)}")
                if attempt < max_retries - 1:
                    await random_delay(3, 5)  # 增加等待时间
                    # 在无头模式下，可能需要刷新页面重试
                    if headless and attempt == 2:
                        print("    🔄 刷新页面重试...")
                        await page.reload()
                        await page.wait_for_load_state('networkidle', timeout=10000)
                        await random_delay(2, 3)

        if not upload_success:
            # 保存最终的调试截图
            try:
                await page.screenshot(path="debug_final.png")
                print("📸 已保存最终调试截图: debug_final.png")
            except:
                pass
            raise Exception("无法定位到文件上传输入元素，请检查页面结构或尝试有头模式")

        await random_delay(1, 2)

        # 4. 填写标题和话题（模拟人类打字）
        print("\n步骤 3: 填写标题和话题...")
        await page.locator("div.input-editor").click()
        await random_delay(0.3, 0.8)

        # 模拟人类打字输入标题
        for char in title:
            await page.keyboard.type(char)
            if ANTI_DETECT_CONFIG["random_typing_delay"]:
                await asyncio.sleep(random.uniform(0.05, 0.2))

        await page.keyboard.press("Enter")
        await random_delay(0.5, 1)

        # 填写话题标签
        for tag in tags[:5]:
            await page.keyboard.type("#" + tag)
            if ANTI_DETECT_CONFIG["random_typing_delay"]:
                await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.keyboard.press("Space")
            await random_delay(0.3, 0.6)

        print(f"✅ 已填写标题和 {len(tags[:5])} 个话题")

        # 5. 随机鼠标移动
        await random_mouse_movement(page)

        # 6. 添加到合集
        print("\n步骤 4: 设置合集和原创...")
        await add_collection(page)
        await random_delay(0.5, 1)

        # 7. 添加原创声明
        await add_original(page)
        await random_delay(0.5, 1)

        # 8. 随机鼠标移动
        await random_mouse_movement(page)

        # 9. 等待视频上传完成
        print("\n步骤 5: 等待视频上传完成...")
        max_wait = 300  # 最多等待5分钟
        for i in range(max_wait):
            try:
                # 检查发布按钮是否可用
                publish_button = page.get_by_role("button", name="发表")
                button_class = await publish_button.get_attribute('class')

                if "weui-desktop-btn_disabled" not in button_class:
                    print("✅ 视频上传完成")
                    break

                # 检查是否上传出错
                if await page.locator('div.status-msg.error').count():
                    print("❌ 视频上传出错")
                    return False

                if i % 10 == 0:
                    print(f"  上传中... ({i}/{max_wait}秒)")
                    # 偶尔移动鼠标
                    if i % 30 == 0:
                        await random_mouse_movement(page)

                await asyncio.sleep(1)

            except Exception as e:
                if i % 10 == 0:
                    print(f"  上传中... ({i}/{max_wait}秒)")
                await asyncio.sleep(1)
        else:
            raise Exception("视频上传超时")

        # 10. 发布前随机延迟
        await random_delay(1, 3)

        # 11. 发布视频
        print("\n步骤 6: 发布视频...")
        publish_button = page.locator('div.form-btns button:has-text("发表")')
        if await publish_button.count():
            await publish_button.click()
            await random_delay(0.5, 1)
            print("✅ 点击发表按钮")

        # 等待发布成功
        for i in range(30):
            try:
                await page.wait_for_url("https://channels.weixin.qq.com/platform/post/list", timeout=2000)
                print("✅ 视频发布成功！")

                # 保存更新后的 cookies
                await context.storage_state(path=str(COOKIE_FILE))
                print("✅ Cookie 已更新并保存\n")
                return True
            except:
                current_url = page.url
                if "https://channels.weixin.qq.com/platform/post/list" in current_url:
                    print("✅ 视频发布成功！")

                    # 保存更新后的 cookies
                    await context.storage_state(path=str(COOKIE_FILE))
                    print("✅ Cookie 已更新并保存\n")
                    return True

                print(f"  发布中... ({i+1}/30)")
                await asyncio.sleep(1)

        raise Exception("发布超时")

    except Exception as e:
        print(f"\n❌ 上传失败: {e}\n")
        return False


async def batch_upload(headless=False):
    """批量上传视频（单实例）"""

    print("\n" + "="*50)
    print("🎬 微信视频号批量上传工具（防风控版）")
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

    # 创建唯一的用户数据目录，避免配置文件冲突
    user_data_dir = get_unique_user_data_dir(CHROME_CONFIG["user_data_dir"])

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
                    '--disable-web-security',                    # 禁用网络安全
                    '--disable-features=VizDisplayCompositor',   # 禁用显示合成器
                    '--disable-ipc-flooding-protection',         # 禁用IPC洪水保护
                    '--disable-hang-monitor',                    # 禁用挂起监控
                    '--disable-prompt-on-repost',                # 禁用重新提交提示
                    '--force-color-profile=srgb',                # 强制颜色配置文件
                    '--metrics-recording-only',                  # 仅记录指标
                    '--no-first-run',                            # 跳过首次运行
                    '--enable-automation',                       # 启用自动化
                    '--disable-sync',                            # 禁用同步
                    '--disable-translate',                       # 禁用翻译
                    '--hide-scrollbars',                         # 隐藏滚动条
                    '--mute-audio',                              # 静音音频
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
                    title, tags = generate_title_and_tags(video_path, platform="tencent")

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
    print("🎬 测试上传单个视频")
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

            # 注入反检测脚本
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            # 生成标题和标签
            title, tags = generate_title_and_tags(video_path, platform="tencent")

            # 上传视频
            success = await upload_single_video(page, context, video_path, title, tags, 1, 1)

            await browser.close()
            return success

        except Exception as e:
            print(f"\n❌ 测试失败: {e}\n")
            return False


# ==================== 主入口 ====================
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
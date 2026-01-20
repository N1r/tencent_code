"""
统一的 Cookie 获取脚本
支持抖音创作者平台和微信视频号平台
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

# 获取当前脚本所在目录
SCRIPT_DIR = Path(__file__).parent
COOKIES_DIR = SCRIPT_DIR / "cookies"

# 本地Chrome配置
CHROME_CONFIG = {
    "auto_detect": True,  # 自动检测Chrome路径
    "custom_path": None,  # 自定义Chrome路径，如果auto_detect为False则使用此路径
    "user_data_dir": SCRIPT_DIR / "chrome_data" / "cookies",  # 基础用户数据目录
}


# ==================== 配置区 ====================
PLATFORMS = {
    "douyin": {
        "name": "抖音创作者平台",
        "url": "https://creator.douyin.com/",
        "cookie_file": COOKIES_DIR / "douyin_cookies.json",
    },
    "weixin": {
        "name": "微信视频号",
        "url": "https://channels.weixin.qq.com/login.html",
        "cookie_file": COOKIES_DIR / "weixin_cookies.json",
    }
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


def normalize_cookies_file(cookie_file_path):
    """
    规范化cookies文件格式，确保为数组格式

    参数:
        cookie_file_path (Path): Cookie文件路径

    返回:
        bool: 是否成功规范化
    """
    if not cookie_file_path.exists():
        return False

    try:
        with open(cookie_file_path, 'r', encoding='utf-8') as f:
            cookies_data = json.load(f)

        # 处理不同格式的cookies数据
        if isinstance(cookies_data, list):
            # 已经是数组格式，无需处理
            cookies = cookies_data
        elif isinstance(cookies_data, dict) and "cookies" in cookies_data:
            # 对象格式，提取cookies数组
            cookies = cookies_data["cookies"]
            print(f"🔄 检测到对象格式Cookie文件，正在转换为数组格式...")
        else:
            print(f"❌ Cookie文件格式不支持: {cookie_file_path}")
            return False

        # 确保cookies是数组格式
        if not isinstance(cookies, list):
            print(f"❌ Cookie数据不是数组格式: {cookie_file_path}")
            return False

        # 重新保存为数组格式
        cookie_file_path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))
        print(f"✅ Cookie文件已规范化: {cookie_file_path} ({len(cookies)} 个Cookie)")

        return True

    except json.JSONDecodeError:
        print(f"❌ Cookie文件JSON格式错误: {cookie_file_path}")
        return False
    except Exception as e:
        print(f"❌ 规范化Cookie文件时发生错误: {e}")
        return False


# ==================== 核心功能 ====================
async def get_platform_cookie(platform_key, headless=False):
    """
    获取指定平台的 Cookie

    参数:
        platform_key (str): 平台标识 ('douyin' 或 'weixin')
        headless (bool): 是否使用无头模式

    返回:
        bool: 是否成功获取 Cookie
    """
    if platform_key not in PLATFORMS:
        print(f"❌ 不支持的平台: {platform_key}")
        return False

    platform = PLATFORMS[platform_key]
    platform_name = platform["name"]
    platform_url = platform["url"]
    cookie_file = platform["cookie_file"]

    print(f"\n{'='*50}")
    print(f"获取 {platform_name} Cookie")
    print(f"{'='*50}")

    try:
        # 确保 cookies 目录存在
        COOKIES_DIR.mkdir(exist_ok=True)

        print(f"\n🌐 目标网址: {platform_url}")
        print(f"📂 Cookie 保存路径: {cookie_file}")
        print("🚀 正在打开浏览器...\n")

        # 获取Chrome路径
        chrome_path = get_chrome_path()
        if not chrome_path:
            return False

        # 创建唯一的用户数据目录，避免配置文件冲突
        user_data_dir = get_unique_user_data_dir(CHROME_CONFIG["user_data_dir"])

        async with async_playwright() as p:
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
                args=browser_args
            )

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

            # 打开登录页面
            print("📄 正在加载页面...")
            await page.goto(platform_url)

            print(f"💡 请在浏览器中完成登录操作")
            print("💡 登录完成后，在终端按 Enter 键保存 Cookie\n")

            # 等待用户按 Enter
            input("按 Enter 键保存 Cookie 并关闭浏览器...")

            # 等待一小段时间确保 cookies 完全加载
            await asyncio.sleep(1)

            # 获取所有 cookies
            cookies = await context.cookies()

            # 确保cookies是数组格式
            if not isinstance(cookies, list):
                print(f"\n❌ 获取到的Cookie格式错误")
                return False

            # 保存 cookies 到文件（直接保存数组格式）
            cookie_file.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))

            print(f"\n✅ {platform_name} Cookie 保存成功！")
            print(f"📁 已保存到: {cookie_file}")
            print(f"📊 共保存 {len(cookies)} 个 Cookie\n")

            await context.close()
            return True

    except Exception as e:
        print(f"\n❌ 获取 Cookie 时发生错误: {e}\n")
        return False


async def get_all_cookies(headless=False):
    """获取所有平台的 Cookie"""
    print("\n" + "="*50)
    print("批量获取平台 Cookie")
    print("="*50)

    results = {}

    for index, platform_key in enumerate(PLATFORMS.keys(), 1):
        print(f"\n▶ [{index}/{len(PLATFORMS)}] 处理平台...")
        success = await get_platform_cookie(platform_key, headless)
        results[platform_key] = success

        # 平台间添加间隔
        if platform_key != list(PLATFORMS.keys())[-1]:
            print("\n" + "-"*50 + "\n")
            await asyncio.sleep(2)

    # 输出结果统计
    print("\n" + "="*50)
    print("Cookie 获取结果")
    print("="*50)

    for platform_key, success in results.items():
        platform = PLATFORMS[platform_key]
        platform_name = platform["name"]
        status = "✅ 成功" if success else "❌ 失败"
        file_path = str(platform["cookie_file"])
        print(f"{platform_name}: {status} - {file_path}")

    # 显示后续步骤提示
    success_count = sum(1 for s in results.values() if s)
    if success_count > 0:
        print("\n🎉 Cookie 获取完成！")
        print("💡 下一步：使用这些 Cookie 进行视频上传\n")


# ==================== 主入口 ====================
def main():
    """主函数"""
    print("\n" + "="*50)
    print("🎬 平台 Cookie 获取工具")
    print("自动从浏览器获取并保存登录凭证")
    print("="*50)

    # 显示选项
    print("\n选项:")
    print("  1 - 抖音创作者平台")
    print("  2 - 微信视频号")
    print("  3 - 获取所有平台")
    print("  4 - 修复Cookie文件格式")

    try:
        choice = input("\n请选择操作 [1/2/3/4] (默认: 1): ").strip() or "1"

        if choice not in ["1", "2", "3", "4"]:
            print("❌ 无效的选择")
            return

        # 询问是否使用无头模式
        headless_choice = input("是否使用无头模式 [y/n] (默认: n): ").strip().lower() or "n"
        headless = headless_choice == "y"

        if headless:
            print("💡 使用无头模式运行\n")
        else:
            print("💡 将打开浏览器窗口\n")

        if choice == "1":
            asyncio.run(get_platform_cookie("douyin", headless))
        elif choice == "2":
            asyncio.run(get_platform_cookie("weixin", headless))
        elif choice == "3":
            asyncio.run(get_all_cookies(headless))
        elif choice == "4":
            # 修复Cookie文件格式
            print("\n🔧 修复Cookie文件格式")
            success_count = 0
            total_count = 0

            for platform_key in PLATFORMS.keys():
                platform = PLATFORMS[platform_key]
                cookie_file = platform["cookie_file"]
                total_count += 1

                if normalize_cookies_file(cookie_file):
                    success_count += 1

            print(f"\n📊 修复结果: {success_count}/{total_count} 个文件修复成功")
            if success_count > 0:
                print("✅ Cookie文件格式已修复，可以正常使用了")
            else:
                print("⚠️ 没有需要修复的文件")

    except KeyboardInterrupt:
        print("\n\n⚠️  操作被取消\n")
    except Exception as e:
        print(f"\n💥 程序异常: {e}\n")


if __name__ == '__main__':
    main()

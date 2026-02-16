import asyncio
import json
import os
import sys
import platform
import shutil
import time
from pathlib import Path

# 第三方库
from playwright.async_api import async_playwright
try:
    from pyvirtualdisplay import Display
    HAS_XVFB = True
except ImportError:
    HAS_XVFB = False

from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

# ==================== 配置区 ====================
console = Console(theme=Theme({"info": "cyan", "warning": "yellow", "error": "bold red", "success": "bold green"}))

SCRIPT_DIR = Path(__file__).parent
COOKIES_FILE = SCRIPT_DIR / "cookies" / "douyin_cookies.json"
USER_DATA_DIR = SCRIPT_DIR / "browser_data" / "douyin_profile" 
QR_CODE_PATH = SCRIPT_DIR / "login_qrcode.png"

COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

USE_XVFB = True if platform.system() == "Linux" else False
HEADLESS = False 

# ==================== 辅助函数 ====================

async def inject_stealth(context):
    await context.add_init_script("""
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) { return 'Google Inc. (NVIDIA)'; }
            if (parameter === 37446) { return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti Direct3D11 vs_5_0 ps_5_0, or similar)'; }
            return getParameter(parameter);
        };
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
    """)

def get_chrome_path():
    if platform.system() == "Linux":
        for p in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/bin/google-chrome-stable"]:
            if os.path.exists(p): return p
        return shutil.which("google-chrome-stable")
    elif platform.system() == "Windows":
        return r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    return None

# ==================== 主逻辑 ====================

async def main():
    display = None
    if USE_XVFB and HAS_XVFB:
        console.print("[info]🖥️ 启动虚拟显示器 (Xvfb)...[/info]")
        display = Display(visible=0, size=(1920, 1080))
        display.start()

    try:
        console.clear()
        console.print(Panel.fit("[bold white]🍪 抖音服务端 Cookie 获取工具 (加强验证版)[/bold white]", style="blue"))

        async with async_playwright() as p:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            args = [
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled", 
                "--disable-infobars", "--window-size=1920,1080", "--start-maximized",
                "--disable-dev-shm-usage", "--no-zygote"
            ]

            console.print(f"[dim]📂 加载环境: {USER_DATA_DIR.name}[/dim]")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                executable_path=get_chrome_path(),
                headless=HEADLESS, 
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                args=args
            )
            
            await inject_stealth(context)
            page = await context.new_page()

            console.print("[info]🔗 正在访问登录页...[/info]")
            try:
                # 强制去首页，如果有缓存登录态会自动跳转，没有则显示登录
                await page.goto("https://creator.douyin.com/creator-micro/home", timeout=60000)
            except Exception as e:
                console.print(f"[error]❌ 页面加载出错: {e}[/error]")
                return

            await asyncio.sleep(5)

            # --- 严格判断是否需要登录 ---
            # 1. 检查是否有扫码登录文本
            has_qr_text = await page.get_by_text("扫码登录").count() > 0
            # 2. 检查是否有头像元素 (代表已登录)
            has_avatar = await page.locator(".avatar-container").count() > 0 or await page.locator(".header-right").count() > 0
            
            if has_avatar and not has_qr_text:
                console.print("[success]✅ 检测到头像，当前已经是登录状态！[/success]")
            else:
                console.print("[warning]🔒 未检测到登录状态，准备截图...[/warning]")
                
                # 截图前多等一会，确保二维码刷出来
                await asyncio.sleep(3)
                try:
                    await page.screenshot(path=QR_CODE_PATH, full_page=True)
                except Exception as e:
                    console.print(f"[error]截图失败: {e}[/error]")

                console.print(Panel(f"""
[bold green]二维码已保存至: {QR_CODE_PATH}[/bold green]

1. 请下载图片 -> 抖音APP扫码 -> 手机确认登录。
2. [bold yellow]脚本正在等待“扫码登录”字样消失...[/bold yellow]
                """, title="操作指南"))

                # --- 循环检测登录状态 (逻辑修改) ---
                start_time = time.time()
                while True:
                    if time.time() - start_time > 300: # 5分钟超时
                        console.print("[error]❌ 扫码超时[/error]")
                        return

                    # 判据1: "扫码登录" 文本必须消失
                    qr_text_visible = await page.get_by_text("扫码登录").is_visible()
                    # 判据2: 必须出现 "内容管理" 或 "首页" 或 "发布视频" 等登录后才有的元素
                    logged_in_element = await page.get_by_text("内容管理").is_visible() or \
                                        await page.get_by_text("发布视频").is_visible() or \
                                        await page.locator(".avatar-container").count() > 0

                    if not qr_text_visible and logged_in_element:
                        console.print("\n[success]🎉 验证成功！检测到登录元素！[/success]")
                        break
                    
                    # 打印当前状态方便调试
                    # print(f"扫码字样: {qr_text_visible}, 登录元素: {logged_in_element}")

                    console.print(".", end="")
                    sys.stdout.flush()
                    await asyncio.sleep(2)

            # 保存 Cookie
            await asyncio.sleep(3) 
            cookies = await context.cookies()
            with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2)
            
            console.print(f"[success]💾 Cookie 已保存至: {COOKIES_FILE}[/success]")
            await context.close()

    except Exception as e:
        console.print(f"[error]发生异常: {e}[/error]")
    finally:
        if display:
            display.stop()
            console.print("[dim]🖥️ 虚拟显示器已关闭[/dim]")

if __name__ == "__main__":
    asyncio.run(main())
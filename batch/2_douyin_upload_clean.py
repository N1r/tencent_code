import asyncio
import json
import random
import os
import shutil
import platform
import requests
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# ==================== 依赖检查 ====================
try:
    from pyvirtualdisplay import Display
    HAS_XVFB = True
except ImportError:
    HAS_XVFB = False
    print("❌ 缺少 pyvirtualdisplay，请运行 pip install pyvirtualdisplay")

# ==================== Rich UI ====================
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.theme import Theme

console = Console(theme=Theme({"success": "bold green", "error": "bold red", "warning": "yellow"}))

# ==================== 路径与配置 ====================
SCRIPT_DIR = Path(__file__).parent
VIDEO_FOLDER = SCRIPT_DIR / "output" / "moved_files/done"
COOKIES_FILE = SCRIPT_DIR / "cookies" / "douyin_cookies.json"
USER_DATA_DIR = SCRIPT_DIR / "browser_data" / "douyin_profile"
STEALTH_JS_PATH = SCRIPT_DIR / "stealth.min.js"

# 归档目录
DONE_DIR = VIDEO_FOLDER / "done"
FAILED_DIR = VIDEO_FOLDER / "failed"
DEBUG_DIR = SCRIPT_DIR / "debug_douyin"

for p in [DONE_DIR, FAILED_DIR, USER_DATA_DIR, DEBUG_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# 【核心配置】
# OpenCloudOS 是 Linux，必须开启 Xvfb
USE_XVFB = True if platform.system() == "Linux" else False
# 必须设为 False，让 Xvfb 接管显示，欺骗抖音我们有显示器
HEADLESS_MODE = False  

# ==================== 工具函数 ====================

def ensure_stealth_js():
    """下载防检测 JS"""
    if not STEALTH_JS_PATH.exists():
        try:
            url = "https://raw.githubusercontent.com/requireCool/stealth.min.js/main/stealth.min.js"
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200:
                with open(STEALTH_JS_PATH, "w", encoding="utf-8") as f: f.write(resp.text)
                console.print("[green]✅ stealth.min.js 下载成功[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ 下载 stealth.min.js 失败: {e}[/yellow]")

async def inject_stealth(context):
    """注入深度指纹伪造"""
    if STEALTH_JS_PATH.exists():
        await context.add_init_script(path=STEALTH_JS_PATH)
    
    # 针对 Linux 服务器的强力伪装
    await context.add_init_script("""
        // 1. 伪装系统平台为 Windows
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        
        // 2. 伪造显卡 (防止被识别为 Linux 服务器常用的 llvmpipe)
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) { return 'Google Inc. (NVIDIA)'; }
            if (parameter === 37446) { return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti Direct3D11 vs_5_0 ps_5_0, or similar)'; }
            return getParameter(parameter);
        };

        // 3. 抹除自动化特征
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

def get_chrome_path():
    """查找 OpenCloudOS 上的 Chrome"""
    if platform.system() == "Linux":
        # OpenCloudOS 安装的 Chrome 通常在这里
        paths = [
            "/usr/bin/google-chrome-stable", 
            "/usr/bin/google-chrome",
            "/bin/google-chrome-stable"
        ]
        for p in paths:
            if os.path.exists(p): return p
        # 如果没找到，尝试 which
        return shutil.which("google-chrome-stable") or shutil.which("chromium-browser")
    return None

async def start_browser(p):
    ensure_stealth_js()
    console.print(f"[dim]📂 加载用户数据: {USER_DATA_DIR.name}[/dim]")

    chrome_path = get_chrome_path()
    if chrome_path:
        console.print(f"[dim]🚀 使用浏览器: {chrome_path}[/dim]")
    else:
        console.print("[yellow]⚠️ 未找到 Google Chrome，将使用 Playwright 自带 Chromium (风险稍高)[/yellow]")

    # 伪装成 Windows Chrome 用户
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled", 
        "--disable-infobars",
        "--window-size=1920,1080",
        "--start-maximized",
        # 禁用一些后台服务以提高在服务器上的稳定性
        "--disable-dev-shm-usage", 
        "--no-zygote",
    ]

    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        executable_path=chrome_path,
        headless=HEADLESS_MODE, # 注意：这里是 False，依赖 Xvfb
        viewport={"width": 1920, "height": 1080},
        user_agent=user_agent,
        args=args,
        device_scale_factor=1,
    )
    
    await inject_stealth(context)
    
    # 加载 Cookie
    if COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE, 'r') as f:
                c = json.load(f)
                await context.add_cookies(c if isinstance(c, list) else c.get('cookies', []))
        except: pass

    return context

# ==================== 行为逻辑 ====================

async def human_behavior(page):
    """简单的拟人操作"""
    try:
        await page.mouse.wheel(0, random.randint(100, 300))
        await asyncio.sleep(random.uniform(0.5, 1.0))
    except: pass

async def warm_up(context):
    """预热：访问首页而非上传页，刷新 Token"""
    console.print("[dim]🧘 正在进行行为预热...[/dim]")
    page = await context.new_page()
    try:
        await page.goto("https://creator.douyin.com/creator-micro/home", timeout=30000)
        await asyncio.sleep(3)
        await human_behavior(page)
        console.print("[green]✅ 预热完成[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠️ 预热跳过: {e}[/yellow]")
    finally:
        await page.close()

async def wait_for_upload_completion(page, file_path):
    console.print("  ⏳ [cyan]上传与转码中...[/cyan]")
    start_time = datetime.now()
    while True:
        if (datetime.now() - start_time).seconds > 300: return False
        try:
            # 随机动动防止挂机判定
            if random.random() < 0.2: await human_behavior(page)

            if await page.locator(':text("重新上传")').count() > 0:
                console.print("  ✅ [green]就绪[/green]")
                return True
            
            if await page.locator(':text("上传失败")').count() > 0:
                console.print("[yellow]⚠️ 上传失败，重试...[/yellow]")
                await page.locator("input[type='file']").set_input_files(str(file_path))
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(2)
        except: await asyncio.sleep(2)

async def upload_video(context, video_path, index, total):
    page = await context.new_page()
    v_name = video_path.stem
    
    try:
        # 1. 访问上传页
        await page.goto("https://creator.douyin.com/creator-micro/content/upload", timeout=45000)
        
        # 登录检测
        if "login" in page.url or await page.get_by_text("扫码登录").count():
            return False, "Cookie 失效"

        console.log(f"[{index}/{total}] 📤 上传: [cyan]{v_name}[/cyan]")

        # 2. 上传文件
        file_input = page.locator("input[type='file']")
        await file_input.wait_for(state="attached", timeout=10000)
        await file_input.set_input_files(str(video_path))

        # 3. 等待完成
        if not await wait_for_upload_completion(page, video_path):
            return False, "超时"

        # 4. 填标题
        await asyncio.sleep(1)
        try:
            # 兼容新旧版定位
            title_box = page.locator(".notranslate")
            if await title_box.count() == 0:
                title_box = page.locator('div[data-placeholder="标题 (必填)"]') # 备用定位
            
            await title_box.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.5)
            await page.keyboard.type(v_name[:30], delay=80) 
            await page.keyboard.press("Enter")
        except Exception as e:
            console.print(f"[yellow]标题填写小问题: {e}[/yellow]")

        # 5. 标签
        tags = ["日常", "记录"]
        for tag in tags:
            await page.keyboard.type(f" #{tag} ", delay=100)
            await asyncio.sleep(0.5)

        # 6. 发布
        console.log("🚀 提交中...")
        await asyncio.sleep(1)
        
        # 尝试点击发布
        if await page.get_by_role('button', name="发布", exact=True).count():
            await page.get_by_role('button', name="发布", exact=True).click()
        else:
            await page.locator('button:has-text("发布")').click()

        await asyncio.sleep(2)
        
        # 7. 自动封面兜底
        if await page.get_by_text("请设置封面").count() > 0:
            console.print("  🎨 处理封面弹窗...")
            await page.locator('[class^="recommendCover-"]').first.click()
            await asyncio.sleep(1)
            # 点击确定
            if await page.get_by_text("确定").count():
                await page.get_by_text("确定").click()
            elif await page.get_by_role("button", name="确定").count():
                await page.get_by_role("button", name="确定").click()

        # 8. 验证
        try:
            await page.wait_for_url("**/content/manage**", timeout=20000)
            console.log("[success]✅ 成功发布[/success]")
            
            # 成功后立即回写 Cookie
            cookies = await context.cookies()
            with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2)
            
            return True, "OK"
        except:
            if await page.get_by_text("发布成功").count(): return True, "OK"
            
            # 调试截图
            await page.screenshot(path=DEBUG_DIR / f"fail_{v_name}.png")
            return False, "未跳转页面"

    except Exception as e:
        await page.screenshot(path=DEBUG_DIR / f"error_{v_name}.png")
        return False, str(e)[:50]
    finally:
        await page.close()

# ==================== 主入口 ====================

async def main():
    display = None
    # 在 Linux 下启动 Xvfb
    if USE_XVFB and HAS_XVFB:
        console.print("[dim]🖥️ 启动 Xvfb 虚拟显示器 (OpenCloudOS)...[/dim]")
        # 必须设置 size，否则默认可能太小导致页面布局错乱
        display = Display(visible=0, size=(1920, 1080))
        display.start()

    try:
        console.clear()
        console.print(Panel.fit("[bold white]🎵 OpenCloudOS 专用上传脚本[/bold white]", style="blue"))

        videos = list(VIDEO_FOLDER.glob("*.mp4"))
        if not videos:
            console.print("[error]❌ 目录无视频[/error]")
            return

        async with async_playwright() as p:
            context = await start_browser(p)
            await warm_up(context)

            with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), console=console) as progress:
                task = progress.add_task("Total", total=len(videos))
                for i, v in enumerate(videos, 1):
                    progress.update(task, description=f"Processing {v.name}")
                    
                    success, msg = await upload_video(context, v, i, len(videos))
                    
                    if success:
                        try: shutil.move(str(v), DONE_DIR / v.name)
                        except: pass
                    else:
                        console.print(f"[red]❌ {v.name}: {msg}[/red]")
                        try: shutil.move(str(v), FAILED_DIR / v.name)
                        except: pass
                        await asyncio.sleep(60) # 失败惩罚时间
                    
                    progress.advance(task)
                    if i < len(videos):
                        # 随机等待 30-50秒
                        await asyncio.sleep(random.randint(30, 50))

            await context.close()
    
    finally:
        if display:
            display.stop()
            console.print("[dim]🖥️ Xvfb 已停止[/dim]")

if __name__ == "__main__":
    asyncio.run(main()) 
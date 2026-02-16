import asyncio
import json
import random
import platform
import os
import shutil
from pathlib import Path
from playwright.async_api import async_playwright

# ==================== Rich 美化库 ====================
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel

# ==================== 配置区 ====================
console = Console()
print = console.print 

# 自动检测系统
SYSTEM = platform.system()

# 路径配置
FOLDER_PATH = Path("output/moved_files")
COVER_FOLDER_PATH = Path("output/moved_files")
COOKIES_FILE = Path("tc_cookies.json")       # 你的 Cookie 源文件
USER_DATA_DIR = Path("browser_data")         # 【新】浏览器持久化数据目录

# 成功/失败归档
DONE_DIR = FOLDER_PATH / "done"
FAILED_DIR = FOLDER_PATH / "failed"
DONE_DIR.mkdir(parents=True, exist_ok=True)
FAILED_DIR.mkdir(parents=True, exist_ok=True)
USER_DATA_DIR.mkdir(parents=True, exist_ok=True) # 确保数据目录存在

# 服务器模式强制无头
HEADLESS_MODE = True

# 封面最小分辨率
MIN_COVER_WIDTH = 752
MIN_COVER_HEIGHT = 360

# 任务统计
TASK_RESULTS = []

# ==================== 工具函数 ====================

async def human_sleep(min_seconds=1, max_seconds=3):
    """模拟人类操作的随机等待"""
    t = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(t)

async def refresh_cookies(context):
    """
    【自动续期核心】
    1. 持久化上下文会自动保存到 user_data_dir
    2. 这里额外将最新 Cookie 导出到 json，方便迁移或备份
    """
    try:
        cookies = await context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
        # console.log("[dim]💾 Cookies 已同步刷新到本地文件[/dim]")
    except Exception as e:
        console.print(f"[red]⚠️ Cookie 刷新失败: {e}[/red]")

def is_valid_image(img_path):
    try:
        from PIL import Image
        with Image.open(img_path) as img:
            w, h = img.size
            return w >= MIN_COVER_WIDTH and h >= MIN_COVER_HEIGHT
    except:
        return False

def find_cover_for_video(video_path, cover_folder):
    video_name = video_path.stem
    for ext in [".png", ".jpg"]:
        cover_path = cover_folder / f"{video_name}{ext}"
        if cover_path.exists() and is_valid_image(cover_path):
            return cover_path
    return None

def move_finished_file(video_path, cover_path, target_dir):
    try:
        shutil.move(str(video_path), target_dir / video_path.name)
        if cover_path and cover_path.exists():
            shutil.move(str(cover_path), target_dir / cover_path.name)
    except Exception as e:
        console.print(f"[red]❌ 文件移动失败: {e}[/red]")

# ==================== 核心上传逻辑 ====================

async def upload_cover_logic(page, cover_path):
    """上传封面"""
    try:
        upload_btn = page.get_by_role("img", name="plus")
        await upload_btn.wait_for(state="visible", timeout=10000)
        await upload_btn.click()
        
        input_el = page.locator("span.ant-upload input[type='file']")
        await input_el.wait_for(state="attached", timeout=10000)
        await input_el.set_input_files(str(cover_path))
        return True
    except Exception as e:
        console.print(f"[red]❌ 上传封面失败: {e}[/red]")
        return False

async def process_cover_crop_logic(page):
    """裁剪逻辑 (严格遵照你的双击逻辑)"""
    try:
        await page.get_by_role("dialog", name="裁剪封面").locator("img").click()
        await human_sleep(0.5, 1)
        # 点击两次未裁剪
        try:
            await page.get_by_text("封面未裁剪").first.click()
            await page.get_by_text("封面未裁剪").click()
        except:
            pass 
        await human_sleep(0.5, 1)
        await page.get_by_role("button", name="完 成").click()
        return True
    except:
        return False

async def upload_single_video(context, video_path, cover_path):
    """单视频处理流程"""
    # 即使是持久化上下文，也建议开新 Page 处理任务，处理完关闭
    page = await context.new_page()

    try:
        # 1. 打开页面
        await page.goto("https://shizi.qq.com/creation/video")
        
        # 检查是否掉登录
        if "login" in page.url:
            return False, "登录失效 (重定向至登录页)"

        # 2. 等待上传入口
        await page.get_by_role("button", name="本地上传").wait_for(state="visible", timeout=20000)
        await human_sleep(2, 4)

        # 3. 上传视频
        console.log(f"📤 正在上传: [cyan]{video_path.name}[/cyan]")
        video_input = page.locator("input[type='file'][accept^='video']")
        await video_input.set_input_files(str(video_path))

        # 【防止假上传 Checkpoint 1】等待上传成功文字
        try:
            await page.locator("text=视频上传成功").wait_for(state="visible", timeout=300000) # 5分钟
            console.log("✅ 视频流传输完毕")
        except:
            return False, "视频上传超时 (网络慢或文件过大)"
        
        await human_sleep(1, 2)

        # 4. 封面处理
        if cover_path:
            console.log(f"🖼️  处理封面: [cyan]{cover_path.name}[/cyan]")
            if await upload_cover_logic(page, cover_path):
                await process_cover_crop_logic(page)
            await human_sleep(1, 2)

        # 5. 原创声明
        try:
            await page.get_by_text("声明原创").click()
            await page.get_by_text("该视频非AI生成").click()
        except:
            pass

        await human_sleep(1, 2)

        # 6. 发布 (双击逻辑)
        console.log("🚀 提交发布...")
        await page.get_by_role("button", name="发 布").click()
        await human_sleep(0.5, 1)
        
        # 处理确认弹窗 或 再次点击
        if await page.get_by_role("button", name="确定发布").is_visible():
            await page.get_by_role("button", name="确定发布").click()
        else:
            publish_btn = page.get_by_role("button", name="发 布")
            if await publish_btn.is_visible():
                await publish_btn.click()
        # 【防止假上传 Checkpoint 2】等待跳转回管理页
        console.log("⏳ 等待服务器响应 (验证中)...")
        try:
            # 只有 URL 变成管理页，才算真正的成功
            await page.wait_for_url("**/content/article-manage**", timeout=25000)
            console.log("[bold green]✅ 发布成功 (页面已跳转)[/bold green]")
        except:
            # 失败截图
            console.log("[bold red]❌ 发布后未跳转，判定为失败[/bold red]")
            await page.screenshot(path=FAILED_DIR / f"fail_{video_path.stem}.png")
            return False, "点击发布后页面卡滞 (疑似假上传)"

        # 成功后，刷新 JSON 文件并让持久化上下文自动保存
        await refresh_cookies(context)
        return True, "发布成功"

    except Exception as e:
        await page.screenshot(path=FAILED_DIR / f"error_{video_path.stem}.png")
        return False, f"异常: {str(e)[:50]}"

    finally:
        await page.close()

# ==================== 浏览器启动 (持久化版) ====================

def get_launch_args():
    return [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled", # 关键防检测
        "--window-size=1920,1080"
    ]

async def start_persistent_browser(p):
    """
    启动持久化浏览器
    1. 使用 browser_data 目录存储状态 (LocalStorage/IndexedDB/Cookies)
    2. 如果有 tc_cookies.json，尝试注入以更新状态
    """
    # 1. 启动持久化上下文
    console.print(f"[dim]📂 加载用户数据: {USER_DATA_DIR}[/dim]")
    
    context = await p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR, # 持久化目录
        headless=HEADLESS_MODE,
        args=get_launch_args(),
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    
    # 注入 webdriver 屏蔽
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # 2. 尝试从 JSON 注入/更新 Cookies (作为补充)
    # 这样如果你在本地提取了新 Cookie，传到服务器上，脚本会自动读进去
    if COOKIES_FILE.exists():
        try:
            json_cookies = json.loads(COOKIES_FILE.read_text())
            await context.add_cookies(json_cookies)
            console.print("[green]🍪 已从 JSON 文件合并最新 Cookies[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ JSON Cookie 读取失败，将使用浏览器缓存: {e}[/yellow]")
    
    return context

# ==================== 主程序 ====================

async def main():
    console.clear()
    console.print(Panel.fit("[bold white]🐧 企鹅号 自动上传 (持久化+严格校验版)[/bold white]", style="blue"))

    # 1. 扫描文件
    videos = list(FOLDER_PATH.glob("*.mp4"))
    if not videos:
        console.print("[bold red]❌ 未找到视频文件[/bold red]")
        return
    console.print(f"[cyan]📊 待处理视频: {len(videos)} 个[/cyan]")

    async with async_playwright() as p:
        # 启动持久化浏览器
        context = await start_persistent_browser(p)
        
        # 2. 登录态预检
        check_page = await context.new_page()
        try:
            await check_page.goto("https://shizi.qq.com/creation/video", timeout=30000)
            await human_sleep(1)
            if "login" in check_page.url:
                console.print("[bold red]⛔ 登录失效！请更新 tc_cookies.json 文件[/bold red]")
                # 即使失败，也尽量不关闭 context，以免破坏现有数据，直接退出
                await context.close()
                return
            console.print("[green]✅ 登录状态有效[/green]")
        except Exception as e:
            console.print(f"[red]❌ 网络或浏览器初始化异常: {e}[/red]")
            await context.close()
            return
        finally:
            await check_page.close()

        # 3. 任务队列
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            task_id = progress.add_task("上传进度", total=len(videos))

            for video_path in videos:
                progress.update(task_id, description=f"处理: {video_path.name}")
                
                cover_path = find_cover_for_video(video_path, COVER_FOLDER_PATH)
                
                # 执行上传
                success, msg = await upload_single_video(context, video_path, cover_path)
                
                if success:
                    console.print(f"[bold green]✅ 成功:[/bold green] {video_path.name}")
                    TASK_RESULTS.append({"name": video_path.name, "status": "成功", "msg": msg})
                    move_finished_file(video_path, cover_path, DONE_DIR)
                else:
                    console.print(f"[bold red]❌ 失败:[/bold red] {video_path.name} -> {msg}")
                    TASK_RESULTS.append({"name": video_path.name, "status": "失败", "msg": msg})
                    move_finished_file(video_path, cover_path, FAILED_DIR)
                
                progress.advance(task_id)
                
                if video_path != videos[-1]:
                    await human_sleep(5, 10)

        # 任务结束，关闭上下文（此时会自动将所有状态写入 user_data_dir）
        await context.close()

    # 4. 报告
    console.print(f"\n[bold]🎉 任务结束[/bold] - 成功: {len([r for r in TASK_RESULTS if r['status']=='成功'])}")

if __name__ == "__main__":
    asyncio.run(main())
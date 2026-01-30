import requests
import yt_dlp
import os

# ================= 1. 目标账号 =================
TARGETS = [
    "acyn.bsky.social",
    "atrupar.com"
]

# # ================= 1. 扩充后的目标账号列表 =================
# TARGETS = [
#     # --- 核心切片大神 ---
#     "acyn.bsky.social",          # Acyn
#     "atrupar.bsky.social",       # Aaron Rupar
#     "ronfilipkowski.bsky.social",# Ron Filipkowski (量大管饱)
#     "patriottakes.bsky.social",  # PatriotTakes (监控右翼)
    
#     # --- 现场搞事/幽默 ---
#     "waltermasterson.bsky.social", # Walter Masterson (集会采访)
#     "thegoodliars.bsky.social",    # The Good Liars
    
#     # --- 犀利名嘴 ---
#     "mehdi.bsky.social",         # Mehdi Hasan (辩论)
#     "meidastouch.bsky.social",   # MeidasTouch (综合)
#     "kamalahq.bsky.social",      # Kamala HQ (官方玩梗)
# ]

# ================= 2. 只需要这个函数找链接 =================
def get_latest_video_links(handle, limit=20):
    # BlueSky API (查个人时间线)
    api_url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
    
    # 先解析 DID (为了稳定性)
    try:
        did = requests.get("https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle", 
                           params={"handle": handle}).json().get("did")
    except:
        print(f"⚠️ 找不到用户: {handle}")
        return []

    print(f"🔍 正在扫描 @{handle} 的最近 {limit} 条内容...")
    
    # 只要带有视频的帖子
    resp = requests.get(api_url, params={
        "actor": did, 
        "limit": limit, 
        "filter": "posts_with_video" # 官方过滤器：只看视频
    }).json()

    links = []
    for item in resp.get("feed", []):
        # 提取 Post ID
        uri = item.get("post", {}).get("uri", "")
        if uri:
            post_id = uri.split("/")[-1]
            # 拼接成标准 URL
            link = f"https://bsky.app/profile/{handle}/post/{post_id}"
            links.append(link)
    
    print(f"   -> 发现 {len(links)} 个视频链接")
    return links

# ================= 3. 直接调用 yt-dlp 下载 =================
def main():
    save_dir = "BlueSky_Downloads"
    
    # 收集所有链接
    all_links = []
    for user in TARGETS:
        all_links.extend(get_latest_video_links(user))

    if not all_links:
        print("没找到视频，结束。")
        return

    print(f"\n🚀 将把 {len(all_links)} 个链接交给 yt-dlp 处理...\n")

    # yt-dlp 配置 (最简单的即可)
    ydl_opts = {
        'outtmpl': f'{save_dir}/%(uploader)s/%(upload_date)s_%(title).100s [%(id)s].%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'ignoreerrors': True,
    }

    # 一键下载所有链接
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(all_links)

if __name__ == "__main__":
    main()
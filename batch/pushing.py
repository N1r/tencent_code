import requests
import sys

# === 请在这里填入你的真实 SendKey ===
# 正确格式：SCT 开头（例如 SCT123456abcdef...）
# 获取地址：https://sct.ftqq.com/
SENDKEY = "sctp14570tvpvdh4gpvae9ra6x4ysdhy"  # ← 替换成你自己的！

# =============================
def test_wechat_push():    # 修复 URL（去除空格！）
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"  # ✅ 无空格

    title = "【测试】YAML 任务完成通知"
    desc = (
        "这是一条测试消息，用于验证微信推送是否正常工作。\n\n"
        "✅ 如果你在微信收到此消息，说明配置成功！\n"
        "❌ 如果没收到，请检查：\n"
        "  1. 是否用 微信 扫码登录 sct.ftqq.com\n"
        "  2. SENDKEY 是否以 SCT 开头\n"
        "  3. 微信是否开启了「服务通知」"
    )

    print(f"正在向 Server酱发送测试消息...")
    print(f"URL: {url}")

    try:
        response = requests.post(
            url,
            data={"title": title, "desp": desc},
            timeout=10
        )
        print(f"HTTP 状态码: {response.status_code}")
        print(f"响应内容: {response.text}")

        if response.status_code == 200:
            try:
                result = response.json()
                if result.get("code") == 0:
                    print("\n✅ 推送成功！请立即查看微信「服务通知」")
                    print("（下拉微信聊天列表，或进入「我 → 服务 → 服务通知」）")
                else:
                    print(f"\n❌ Server酱返回错误: {result.get('msg', '未知错误')}")
                    if result.get("code") == 1001:
                        print("  可能原因：SendKey 无效或已过期")
                    elif result.get("code") == 1002:
                        print("  可能原因：今日免费额度已用完（每天5条）")
            except Exception as e:
                print(f"\n❌ 响应不是 JSON: {e}")
        else:
            print(f"\n❌ HTTP 请求失败，状态码: {response.status_code}")

    except requests.exceptions.Timeout:
        print("\n❌ 请求超时，请检查网络或 Server酱服务状态")
    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到 Server酱，请检查网络")
    except Exception as e:
        print(f"\n❌ 未知错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_wechat_push()
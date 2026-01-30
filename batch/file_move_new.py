import os
import shutil
import time
import requests
from pathlib import Path

# ==================== API 配置 ====================
API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
API_BASE_URL = 'https://api.302.ai'
API_MODEL = 'grok-4-1-fast-non-reasoning'  # 可选: grok-4-1-fast-non-reasoning, gemini-2.5-flash-lite-preview-09-2025

# ==================== 翻译函数 ====================
def translate_with_api(text: str) -> str:
    """
    使用大模型API翻译英文为中文
    如果API调用失败，返回原文
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    # 简化的提示词，专注于视频标题翻译
    prompt = """
你是一名专业的翻译专家，擅长将英文视频标题翻译成简洁、自然、易懂的中文。

任务要求：
1. 翻译结果要简洁明了，符合中文表达习惯, 采取中国人民喜闻乐见的表述和用语.
2. 保持原意的同时，让标题更吸引人
3. 字数控制在15-25个汉字
4. 只返回翻译后的标题，不要其他解释或符号

输出格式：
- 仅输出一行中文标题
- 不要加引号、不要换行、不要添加任何前缀
"""
    
    data = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"请翻译这个标题：{text}"}
        ],
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/chat/completions", 
            headers=headers, 
            json=data, 
            timeout=30
        )
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"].strip()
        
        # 清理可能的引号和多余符号
        result = result.strip('"\'""''')
        
        print(f"  API翻译: {text[:50]}... -> {result}")
        
        # 添加短暂延迟，避免请求过快
        time.sleep(0.3)
        return result
        
    except Exception as e:
        print(f"  ⚠️ API翻译失败: {e}，使用原文")
        return text

def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除不合法字符
    """
    # 移除或替换不合法的文件名字符
    illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in illegal_chars:
        filename = filename.replace(char, '')
    
    # 移除前后空格
    filename = filename.strip()
    
    # 如果文件名为空，使用默认名称
    if not filename:
        filename = "未命名"
    
    return filename

def move_and_rename_files():
    """
    遍历output文件夹下的所有子文件夹
    1. 将文件夹名翻译为中文（使用大模型API）
    2. 将output_sub.mp4重命名为 {中文文件夹名}.mp4
    3. 将所有mp4和包含_new的图片文件复制到moved_files文件夹（使用中文文件名）
    """
    # 设置基础路径
    output_dir = Path("output")
    moved_files_dir = output_dir / "moved_files"
    
    # 创建moved_files文件夹
    moved_files_dir.mkdir(exist_ok=True)
    print(f"✅ 目标文件夹: {moved_files_dir}\n")
    
    # 统计信息
    processed_folders = 0
    processed_files = 0
    
    # 遍历output下的所有子文件夹
    for folder in output_dir.iterdir():
        if not folder.is_dir() or folder.name == "moved_files" or folder.name.startswith('.'):
            continue
        
        folder_name = folder.name
        print(f"\n{'='*60}")
        print(f"处理文件夹: {folder_name}")
        print(f"{'='*60}")
        
        # 使用API翻译文件夹名为中文
        chinese_name = translate_with_api(folder_name)
        chinese_name = sanitize_filename(chinese_name)
        
        print(f"  中文名称: {chinese_name}")
        
        # 查找文件夹根目录下符合条件的文件
        folder_file_count = 0
        for file in folder.iterdir():
            if not file.is_file():
                continue
            
            # 只处理 output_sub.mp4 和 包含_new的图片
            should_process = False
            
            if file.name == "output_sub.mp4":
                should_process = True
            elif file.suffix.lower() in ['.jpg', '.jpeg', '.png'] and '_new' in file.stem:
                should_process = True
            
            if should_process:
                # 确定翻译后的文件名
                if file.name == "output_sub.mp4":
                    # 视频文件使用翻译后的文件夹名
                    chinese_file_name = chinese_name
                else:
                    # 图片文件：移除 _new 后缀后翻译
                    base_name = file.stem.replace('_new', '')
                    chinese_file_name = translate_with_api(base_name)
                    chinese_file_name = sanitize_filename(chinese_file_name)
                
                # 创建目标文件路径
                target_path = moved_files_dir / f"{chinese_file_name}{file.suffix}"
                
                # 如果目标文件已存在，添加数字后缀避免覆盖
                counter = 1
                while target_path.exists():
                    target_path = moved_files_dir / f"{chinese_file_name}_{counter}{file.suffix}"
                    counter += 1
                
                # 复制文件
                shutil.copy2(str(file), str(target_path))
                print(f"  ✅ 复制: {file.name} -> {target_path.name}")
                
                folder_file_count += 1
                processed_files += 1
        
        if folder_file_count > 0:
            processed_folders += 1
        else:
            print(f"  ⚠️  未找到符合条件的文件")
    
    # 输出统计信息
    print(f"\n{'='*60}")
    print(f"✓ 处理完成！")
    print(f"{'='*60}")
    print(f"处理文件夹数: {processed_folders}")
    print(f"处理文件数: {processed_files}")
    print(f"文件位置: {moved_files_dir}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║          视频文件智能翻译与整理工具                        ║
║          使用 AI 模型进行标题翻译                          ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    try:
        move_and_rename_files()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
    except Exception as e:
        print(f"\n\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
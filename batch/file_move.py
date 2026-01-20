import os
import shutil
import time
from pathlib import Path
from deep_translator import GoogleTranslator

def translate_to_chinese(text):
    """
    使用 Google 翻译将英文翻译为中文
    如果翻译失败，返回原文
    """
    try:
        translator = GoogleTranslator(source='en', target='zh-CN')
        translated = translator.translate(text)
        print(f"  翻译: {text} -> {translated}")
        # 添加短暂延迟，避免请求过快
        time.sleep(0.5)
        return translated
    except Exception as e:
        print(f"  ⚠️ 翻译失败: {e}，使用原文名")
        return text

def sanitize_filename(filename):
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
    1. 将文件夹名翻译为中文
    2. 将output_sub.mp4重命名为 {中文文件夹名}.mp4
    3. 将所有mp4和jpg文件复制到moved_files文件夹（使用中文文件名）
    """
    # 设置基础路径
    output_dir = Path("output")
    moved_files_dir = output_dir / "moved_files"

    # 创建moved_files文件夹
    moved_files_dir.mkdir(exist_ok=True)

    # 遍历output下的所有子文件夹
    for folder in output_dir.iterdir():
        if not folder.is_dir() or folder.name == "moved_files" or folder.name.startswith('.'):
            continue

        folder_name = folder.name
        print(f"\n处理文件夹: {folder_name}")

        # 翻译文件夹名为中文
        chinese_name = translate_to_chinese(folder_name)
        chinese_name = sanitize_filename(chinese_name)

        # 查找文件夹根目录下符合条件的文件
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
                # 翻译文件名（不包含扩展名）
                file_stem = file.stem

                # 如果是 output_sub.mp4，使用翻译后的文件夹名
                if file.name == "output_sub.mp4":
                    chinese_file_name = chinese_name
                else:
                    # 移除 _new 后缀后翻译
                    base_name = file_stem.replace('_new', '')
                    chinese_file_name = translate_to_chinese(base_name)
                    chinese_file_name = sanitize_filename(chinese_file_name)

                # 创建目标文件路径
                target_path = moved_files_dir / f"{chinese_file_name}{file.suffix}"

                # 如果目标文件已存在，添加数字后缀避免覆盖
                counter = 1
                while target_path.exists():
                    target_path = moved_files_dir / f"{chinese_file_name}_{counter}{file.suffix}"
                    counter += 1

                shutil.copy2(str(file), str(target_path))
                print(f"  复制: {file.name} -> moved_files/{target_path.name}")

    print("\n✓ 所有文件处理完成!")
    print(f"文件已复制到: {moved_files_dir}")

if __name__ == "__main__":
    move_and_rename_files()

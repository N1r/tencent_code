"""
通用工具函数模块
提供文件查找、标题生成等通用功能
"""
import os
from pathlib import Path
from datetime import datetime


def find_files_by_extension(root_folder, extension, sort_by_date=False, reverse=False):
    """
    在指定文件夹及其子文件夹中查找指定扩展名的文件

    参数:
        root_folder (str): 要搜索的根文件夹路径
        extension (str): 文件扩展名，如 '.mp4', '.png'
        sort_by_date (bool): 是否按文件修改日期排序
        reverse (bool): 是否倒序排序（最新的在前）

    返回:
        list: 包含所有匹配文件的绝对路径列表
    """
    root_folder = Path(root_folder)

    if not root_folder.exists():
        raise FileNotFoundError(f"文件夹不存在: {root_folder}")

    # 查找所有指定扩展名的文件
    pattern = f"*{extension}" if extension.startswith('.') else f"*.{extension}"
    files = [os.path.abspath(file) for file in root_folder.rglob(pattern)]

    # 按修改日期排序
    if sort_by_date:
        files.sort(key=os.path.getmtime, reverse=reverse)

    return files


def find_mp4_files(root_folder, sort_by_date=False, reverse=False):
    """查找所有 MP4 视频文件"""
    return find_files_by_extension(root_folder, '.mp4', sort_by_date, reverse)


def find_png_files(root_folder, sort_by_date=False, reverse=False):
    """查找所有 PNG 图片文件"""
    return find_files_by_extension(root_folder, '.png', sort_by_date, reverse)


def find_jpg_files(root_folder, sort_by_date=False, reverse=False):
    """查找所有 JPG 图片文件"""
    return find_files_by_extension(root_folder, '.jpg', sort_by_date, reverse)


def generate_title_and_tags(filename, platform="douyin"):
    """
    根据文件名生成标题和标签

    参数:
        filename (str): 文件路径或文件名
        platform (str): 平台类型 ('douyin' 或 'tencent')

    返回:
        tuple: (标题, 标签列表)
    """
    # 提取文件名（不含路径和扩展名）
    base_name = Path(filename).stem

    # 处理 Windows 路径中的反斜杠
    if '\\' in base_name:
        base_name = base_name.split('\\')[-1]

    # 生成标题
    current_date = datetime.now().strftime("%Y-%m-%d")
    title = f"{base_name} | {current_date} | 双语字幕"

    # 根据平台生成不同的标签
    if platform == "douyin":
        tags_str = '#知识 #英语听力 #英语新闻 #英语学习'
    elif platform == "tencent":
        tags_str = '#知识 #英语听力 #英语新闻 #英语学习'
    else:
        tags_str = '#英语学习'

    # 将标签字符串转换为列表
    tags = tags_str.replace("#", "").split()

    return title, tags


def save_file_list(files, output_file="file_list.txt"):
    """
    将文件列表保存到文本文件

    参数:
        files (list): 文件路径列表
        output_file (str): 输出文件名
    """
    with open(output_file, "w", encoding="utf-8") as f:
        for file_path in files:
            f.write(f"{file_path}\n")

    print(f"✅ 文件列表已保存到: {output_file}")
    return output_file

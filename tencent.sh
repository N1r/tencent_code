#!/bin/bash

# ================= 基础设置 =================
# 设置编码（Linux 默认通常为 UTF-8）
export PYTHONIOENCODING=utf-8

# ================= 第二步：切换目录 =================
[cite_start]echo -e "\n[2/5] 正在切换工作目录..." [cite: 4]
# 请修改为你的项目实际绝对路径
BASE_DIR="VideoLingo-3.0.0"
cd "$BASE_DIR" || { echo "错误: 无法进入目录 $BASE_DIR"; exit 1; }
echo "   - 当前工作目录已锁定为: $(pwd)"

# ================= 第三步：激活环境 =================
[cite_start]echo -e "\n[3/5] 正在激活 Conda 环境 (videolingo2)..." [cite: 5]
# 初始化 conda（确保脚本能识别 conda 命令）
source "$(conda info --base)/etc/profile.d/conda.sh"

if conda activate videolingo2; then
    echo "   - [成功] 环境激活完成。"
else
    echo "   - [警告] 环境激活失败，尝试继续运行..."
fi

# ================= 第四步：设置路径 =================
[cite_start]echo -e "\n[4/5] 配置 Python 运行环境..." [cite: 6]
export PYTHONPATH=$(pwd)
echo "   - 已将当前目录加入 PYTHONPATH，防止模块报错。"

# ================= 第五步：运行程序 =================
[cite_start]echo -e "\n[5/5] 启动 Python 主程序 (Batch Processor)..." [cite: 7]
echo "-------------------------------------------------------"

# 1. 运行主处理脚本
python3 batch/utils/batch_processor.py

# 2. 切换到 batch 目录运行后续任务
cd batch || exit

# 3. 切换环境并运行上传脚本
conda activate uploader
python3 acc3.py

# 4. 执行 biliup 上传
# 注意：Linux 下 biliup 通常没有 .exe 后缀，确保该文件有执行权限
./biliup upload -c free_content.yaml
./biliup upload -c paid_content.yaml

echo -e "\n-------------------------------------------------------"
[cite_start]echo "[完成] 所有任务执行完毕。" [cite: 8]
#!/bin/bash
# =============================================================================
# Nemotron v2 转 ChatML 格式脚本
# 将 Nemotron-Post-Training-Dataset-v2 的主要 splits 转换为 JSONL 格式
# =============================================================================

set -e  # 遇到错误立即退出

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 激活虚拟环境
source "$PROJECT_ROOT/.venv/bin/activate"

# 设置 PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo "=========================================="
echo "Nemotron v2 数据集转换为 ChatML 格式"
echo "=========================================="

# 运行 ChatML 转换任务
# 注意：这将转换所有 splits (chat, code, math, stem, multilingual_*)
python -m modelcall run-task \
    configs/tasks/data_distillation/20251015/convert_nemotron_v2_chatml.yaml

echo ""
echo "=========================================="
echo "✅ 转换完成！"
echo "=========================================="
echo "输出目录: /volume/pt-train/users/wzhang/coder/coder-data/dataset/prepared"
echo "文件格式: nvidia_Nemotron-Post-Training-Dataset-v2-{split}-train.jsonl"
echo "=========================================="


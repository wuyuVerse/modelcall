#!/bin/bash
# =============================================================================
# oo1.jsonl 转 ChatML 格式脚本
# 将 oo1.jsonl (prompt_text 字段) 转换为 ChatML JSONL
# =============================================================================

set -e  # 遇到错误立即退出

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 激活虚拟环境
source "$PROJECT_ROOT/.venv/bin/activate"

# 设置 PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo "=========================================="
echo "oo1.jsonl 数据集转换为 ChatML 格式"
echo "=========================================="

# 运行 ChatML 转换任务
python -m modelcall run-task \
    configs/tasks/data_distillation/20251015/convert_oo1_chatml.yaml

echo ""
echo "=========================================="
echo "✅ 转换完成！"
echo "=========================================="
echo "输出目录: /volume/pt-train/users/wzhang/coder/coder-data/dataset/prepared/oo1"
echo "文件格式: oo1-train.jsonl"
echo "=========================================="



#!/bin/bash
# =============================================================================
# Llama-Nemotron 转 ChatML 格式脚本
# 将 Llama-Nemotron-Post-Training-Dataset 的 SFT 和 RL 数据转换为 ChatML JSONL
# =============================================================================

set -e  # 遇到错误立即退出

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 激活虚拟环境
source "$PROJECT_ROOT/.venv/bin/activate"

# 设置 PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo "=========================================="
echo "Llama-Nemotron 数据集转换为 ChatML 格式"
echo "=========================================="
echo ""
echo "数据集位置: /volume/pt-train/users/wzhang/hf/datasets/nvidia/Llama-Nemotron-Post-Training-Dataset"
echo "输出目录: /volume/pt-train/users/wzhang/coder/coder-data/dataset/prepared"
echo ""
echo "将转换以下数据:"
echo "  - SFT/chat/chat.jsonl"
echo "  - SFT/code/code_v1.jsonl, code_v1.1.jsonl"
echo "  - SFT/math/math_v1.jsonl, math_v1.1.jsonl"
echo "  - SFT/safety/safety.jsonl"
echo "  - SFT/science/science.jsonl"
echo "  - RL/instruction_following/instruction_following.jsonl"
echo ""
echo "=========================================="

# 运行 ChatML 转换任务
python -m modelcall run-task \
    configs/tasks/data_distillation/20251015/convert_llama_nemotron_chatml.yaml

echo ""
echo "=========================================="
echo "✅ 转换完成！"
echo "=========================================="
echo "输出目录: /volume/pt-train/users/wzhang/coder/coder-data/dataset/prepared"
echo "文件格式: nvidia_Llama-Nemotron-Post-Training-Dataset-{config}-train.jsonl"
echo "=========================================="


#!/bin/bash
# =============================================================================
# 数据蒸馏任务启动脚本
# =============================================================================
# 用法: 
#   bash scripts/run_distillation_task.sh <config_path>
# 
# 示例:
#   bash scripts/run_distillation_task.sh configs/tasks/data_distillation/20251011/generate_response_gpt_oss.yaml
#   bash scripts/run_distillation_task.sh configs/tasks/data_distillation/20251011/generate_response_qwen3_coder.yaml
# =============================================================================

set -e  # 遇到错误立即退出

# 检查参数
if [ $# -lt 1 ]; then
    echo "❌ 错误: 缺少配置文件路径参数"
    echo ""
    echo "用法: bash $0 <config_path>"
    echo ""
    echo "示例:"
    echo "  bash $0 configs/tasks/data_distillation/20251011/generate_response_gpt_oss.yaml"
    echo "  bash $0 configs/tasks/data_distillation/20251011/generate_response_qwen3_coder.yaml"
    exit 1
fi

CONFIG_PATH=$1

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 项目根目录（scripts的上一级）
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 切换到项目根目录
cd "$PROJECT_ROOT"

echo "=========================================="
echo "🚀 数据蒸馏任务启动"
echo "=========================================="
echo "📁 项目路径: $PROJECT_ROOT"
echo "📄 配置文件: $CONFIG_PATH"
echo ""

# 检查配置文件是否存在
if [ ! -f "$CONFIG_PATH" ]; then
    echo "❌ 错误: 配置文件不存在: $CONFIG_PATH"
    exit 1
fi

# 检查虚拟环境
VENV_PATH="$PROJECT_ROOT/.venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ 错误: 虚拟环境不存在: $VENV_PATH"
    echo "请先创建虚拟环境"
    exit 1
fi

echo "🔧 激活虚拟环境: $VENV_PATH"
source "$VENV_PATH/bin/activate"

# 验证Python环境
if ! command -v python &> /dev/null; then
    echo "❌ 错误: Python未找到"
    exit 1
fi

echo "🐍 Python版本: $(python --version)"
echo ""

# 显示配置文件内容摘要
echo "=========================================="
echo "📋 任务配置摘要"
echo "=========================================="
python << EOF
import yaml
with open('$CONFIG_PATH', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
print(f"任务名称: {config.get('task_name', 'N/A')}")
print(f"任务类型: {config.get('task_type', 'N/A')}")
print(f"任务描述: {config.get('description', 'N/A')}")
if 'distillation' in config:
    d = config['distillation']
    print(f"蒸馏步骤: {d.get('step', 'N/A')}")
    print(f"模型配置: {d.get('response_config_path', 'N/A')}")
    print(f"输入路径: {d.get('input_path', 'N/A')}")
    print(f"输出路径: {d.get('output_path', 'N/A')}")
    print(f"并发数: {d.get('concurrency', 'N/A')}")
    print(f"批量大小: {d.get('batch_size', 'N/A')}")
    print(f"断点续传: {d.get('resume_mode', 'N/A')}")
EOF
echo ""
echo "=========================================="
echo "⚡ 开始执行任务"
echo "=========================================="
echo ""

# 设置PYTHONPATH并执行任务（使用统一入口 modelcall.run-task）
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
python -m modelcall run-task "$CONFIG_PATH"

# 检查执行结果
EXIT_CODE=$?
echo ""
echo "=========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 任务执行成功!"
else
    echo "❌ 任务执行失败 (退出码: $EXIT_CODE)"
fi
echo "=========================================="

exit $EXIT_CODE


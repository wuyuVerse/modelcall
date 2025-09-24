#!/usr/bin/env bash
# =============================================================================
# 统一任务执行脚本
# =============================================================================

set -euo pipefail

# 获取脚本参数
TASK_CONFIG="${1:-}"
JOB_INDEX="${2:-0}"
WORLD_SIZE="${3:-1}"

# 帮助信息
if [ -z "$TASK_CONFIG" ] || [ "$TASK_CONFIG" = "-h" ] || [ "$TASK_CONFIG" = "--help" ]; then
    echo "📋 ModelCall 任务执行器"
    echo ""
    echo "用法:"
    echo "  $0 <task_config> [job_index] [world_size]"
    echo ""
    echo "参数:"
    echo "  task_config  任务配置文件路径 (configs/tasks/*.yaml)"
    echo "  job_index    作业索引 (默认: 0)"
    echo "  world_size   总作业数 (默认: 1)"
    echo ""
    echo "示例:"
    echo "  # 运行单节点任务"
    echo "  $0 configs/tasks/github_code_rating.yaml"
    echo ""
    echo "  # 运行分布式任务 (节点1/5)"
    echo "  $0 configs/tasks/distributed_rating.yaml 0 5"
    echo ""
    echo "可用任务配置:"
    for config in configs/tasks/*.yaml; do
        if [ -f "$config" ]; then
            task_name=$(basename "$config" .yaml)
            echo "  - $task_name ($config)"
        fi
    done
    exit 0
fi

# 检查任务配置文件是否存在
if [ ! -f "$TASK_CONFIG" ]; then
    echo "❌ 任务配置文件不存在: $TASK_CONFIG"
    echo ""
    echo "可用的任务配置:"
    for config in configs/tasks/*.yaml; do
        if [ -f "$config" ]; then
            echo "  - $config"
        fi
    done
    exit 1
fi

# 获取任务名称
TASK_NAME=$(basename "$TASK_CONFIG" .yaml)

echo "🚀 ModelCall 任务执行器 (后台模式)"
echo "📋 任务配置: $TASK_CONFIG"
echo "🏷️  任务名称: $TASK_NAME"
echo "🌐 作业配置: $JOB_INDEX/$WORLD_SIZE"
echo "⏰ 开始时间: $(date)"

# 创建日志目录
mkdir -p logs

# 后台运行任务，输出重定向到日志文件
LOG_FILE="logs/${TASK_NAME}_$(date +%Y%m%d_%H%M%S)_job${JOB_INDEX}.run.log"

echo "📄 运行日志: $LOG_FILE"
echo "🔄 启动后台任务..."

# 后台运行，同时输出到日志文件和控制台
{
    echo "=== 任务开始 ==="
    echo "任务名称: $TASK_NAME"
    echo "配置文件: $TASK_CONFIG"
    echo "作业配置: $JOB_INDEX/$WORLD_SIZE"
    echo "开始时间: $(date)"
    echo "========================="
    echo ""
    
    uv run modelcall run-task "$TASK_CONFIG" --job_index "$JOB_INDEX" --world_size "$WORLD_SIZE"
    
    echo ""
    echo "=== 任务完成 ==="
    echo "结束时间: $(date)"
    echo "========================="
} > "$LOG_FILE" 2>&1 &

# 获取后台进程ID
TASK_PID=$!

echo "✅ 任务已启动 (PID: $TASK_PID)"
echo "📊 监控命令:"
echo "   tail -f $LOG_FILE                    # 查看运行日志"
echo "   uv run python scripts/utils/view_logs.py --task $TASK_NAME  # 查看任务日志"
echo "   ps -p $TASK_PID                      # 检查进程状态"
echo "   kill $TASK_PID                       # 停止任务"

# 保存PID到文件，方便管理
echo "$TASK_PID" > "logs/${TASK_NAME}_job${JOB_INDEX}.pid"
echo "📁 PID文件: logs/${TASK_NAME}_job${JOB_INDEX}.pid"

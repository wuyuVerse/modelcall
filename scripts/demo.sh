#!/usr/bin/env bash
# =============================================================================
# ModelCall 后台任务演示脚本
# =============================================================================

set -euo pipefail

echo "🎬 ModelCall 统一任务系统演示"
echo ""
echo "本演示将展示："
echo "1. 📋 配置驱动的任务系统"
echo "2. 🔧 自动数据预处理 (支持本地/TOS + JSONL/Parquet输入)"
echo "3. 📊 强制Parquet输出格式"
echo "4. 🚀 自动后台运行"
echo "5. 📈 实时任务监控和管理"
echo ""

# 确保脚本可执行
chmod +x scripts/run_task.sh
chmod +x scripts/manage_tasks.sh

echo "📋 查看可用任务配置:"
find configs/tasks -name "*.yaml" -print0 | sort -z | while IFS= read -r -d $'\0' file; do
    task_name=$(basename "$file" .yaml)
    description=$(grep "description:" "$file" | sed 's/description: *"//' | sed 's/"//')
    echo "  - $task_name: $description"
done

echo ""
echo "🚀 启动演示任务 (debug模式，只处理少量数据)..."

# 启动一个GitHub评分任务（debug模式）
echo "启动任务: github_code_rating (调试模式)"
./scripts/run_task.sh configs/tasks/github_code_rating.yaml &
sleep 2

echo ""
echo "📊 查看运行中的任务:"
./scripts/manage_tasks.sh list

echo ""
echo "💡 可用的管理命令:"
echo "  ./scripts/manage_tasks.sh list                    # 查看所有任务"
echo "  ./scripts/manage_tasks.sh monitor github_code     # 监控任务日志"
echo "  ./scripts/manage_tasks.sh status github_code      # 查看任务状态" 
echo "  ./scripts/manage_tasks.sh stop github_code        # 停止任务"
echo "  ./scripts/manage_tasks.sh stopall                 # 停止所有任务"
echo ""

echo "⏱️  等待3秒后演示监控功能..."
sleep 3

echo ""
echo "📄 演示日志监控 (显示最近几行):"
log_file=$(ls -t logs/*github_code_rating*.run.log 2>/dev/null | head -1 || echo "")
if [ -n "$log_file" ]; then
    echo "最新日志文件: $log_file"
    echo "--- 最近10行 ---"
    tail -10 "$log_file" 2>/dev/null || echo "日志文件还未生成内容"
else
    echo "未找到日志文件，任务可能还在启动中"
fi

echo ""
echo "🛑 停止演示任务..."
./scripts/manage_tasks.sh stop github_code

echo ""
echo "✅ 演示完成！"
echo ""
echo "💡 系统特性:"
echo "  ✅ 配置驱动: 一个YAML文件定义完整任务"
echo "  ✅ 数据格式: 支持JSONL/Parquet输入，强制Parquet输出"
echo "  ✅ 预处理集成: 原始数据自动转换为统一格式(id/text/source)"
echo "  ✅ 后台运行: 所有任务自动后台执行，不阻塞终端"
echo "  ✅ 任务管理: 完整的启动/监控/停止/状态查看功能"
echo "  ✅ 分布式支持: 支持多节点并行处理"
echo ""
echo "🚀 快速开始:"
echo "  ./scripts/run_task.sh configs/tasks/github_raw_code_with_preprocess.yaml"
echo ""
echo "📚 查看完整文档: cat README.md"

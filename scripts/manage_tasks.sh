#!/usr/bin/env bash
# =============================================================================
# 任务管理工具 - 查看、停止、监控后台任务
# =============================================================================

set -euo pipefail

COMMAND="${1:-list}"

case "$COMMAND" in
    "list"|"ls")
        echo "📋 当前运行的任务:"
        echo ""
        
        if [ ! -d "logs" ]; then
            echo "   没有找到logs目录"
            exit 0
        fi
        
        found=false
        for pid_file in logs/*.pid; do
            if [ -f "$pid_file" ]; then
                found=true
                task_name=$(basename "$pid_file" .pid)
                pid=$(cat "$pid_file")
                
                # 检查进程是否还在运行
                if ps -p "$pid" > /dev/null 2>&1; then
                    status="🟢 运行中"
                    # 获取进程启动时间
                    start_time=$(ps -o lstart= -p "$pid" 2>/dev/null | xargs)
                else
                    status="🔴 已停止"
                    start_time="N/A"
                fi
                
                echo "   $task_name"
                echo "     PID: $pid"
                echo "     状态: $status"
                echo "     启动时间: $start_time"
                echo ""
            fi
        done
        
        if [ "$found" = false ]; then
            echo "   没有找到正在运行的任务"
        fi
        ;;
        
    "stop")
        TASK_PATTERN="${2:-}"
        if [ -z "$TASK_PATTERN" ]; then
            echo "❌ 请指定要停止的任务名称模式"
            echo "用法: $0 stop <task_pattern>"
            echo "示例: $0 stop github_code_rating"
            exit 1
        fi
        
        echo "🛑 停止任务: $TASK_PATTERN"
        
        found=false
        for pid_file in logs/*${TASK_PATTERN}*.pid; do
            if [ -f "$pid_file" ]; then
                found=true
                task_name=$(basename "$pid_file" .pid)
                pid=$(cat "$pid_file")
                
                if ps -p "$pid" > /dev/null 2>&1; then
                    echo "   停止任务: $task_name (PID: $pid)"
                    kill "$pid"
                    
                    # 等待进程停止
                    sleep 2
                    if ps -p "$pid" > /dev/null 2>&1; then
                        echo "   强制停止: $task_name"
                        kill -9 "$pid"
                    fi
                    
                    rm -f "$pid_file"
                    echo "   ✅ 已停止: $task_name"
                else
                    echo "   ⚠️  任务已停止: $task_name"
                    rm -f "$pid_file"
                fi
            fi
        done
        
        if [ "$found" = false ]; then
            echo "   ❌ 没有找到匹配的任务: $TASK_PATTERN"
        fi
        ;;
        
    "stopall")
        echo "🛑 停止所有任务"
        
        for pid_file in logs/*.pid; do
            if [ -f "$pid_file" ]; then
                task_name=$(basename "$pid_file" .pid)
                pid=$(cat "$pid_file")
                
                if ps -p "$pid" > /dev/null 2>&1; then
                    echo "   停止任务: $task_name (PID: $pid)"
                    kill "$pid"
                fi
                
                rm -f "$pid_file"
            fi
        done
        
        echo "   ✅ 所有任务已停止"
        ;;
        
    "monitor"|"mon")
        TASK_PATTERN="${2:-}"
        if [ -z "$TASK_PATTERN" ]; then
            echo "❌ 请指定要监控的任务名称模式"
            echo "用法: $0 monitor <task_pattern>"
            exit 1
        fi
        
        # 查找匹配的运行日志文件
        log_file=$(ls -t logs/*${TASK_PATTERN}*.run.log 2>/dev/null | head -1)
        
        if [ -z "$log_file" ]; then
            echo "❌ 没有找到匹配的日志文件: $TASK_PATTERN"
            exit 1
        fi
        
        echo "📄 监控日志: $log_file"
        echo "   (按 Ctrl+C 退出监控)"
        echo ""
        
        tail -f "$log_file"
        ;;
        
    "status")
        TASK_PATTERN="${2:-}"
        if [ -z "$TASK_PATTERN" ]; then
            echo "❌ 请指定要查看状态的任务名称模式"
            echo "用法: $0 status <task_pattern>"
            exit 1
        fi
        
        echo "📊 任务状态: $TASK_PATTERN"
        echo ""
        
        # 查看任务统计
        uv run python scripts/utils/view_logs.py --task "$TASK_PATTERN" --stats 2>/dev/null || {
            echo "   ❌ 没有找到任务统计信息"
        }
        ;;
        
    "clean")
        echo "🧹 清理已停止任务的PID文件"
        
        for pid_file in logs/*.pid; do
            if [ -f "$pid_file" ]; then
                pid=$(cat "$pid_file")
                task_name=$(basename "$pid_file" .pid)
                
                if ! ps -p "$pid" > /dev/null 2>&1; then
                    echo "   清理: $task_name (PID: $pid)"
                    rm -f "$pid_file"
                fi
            fi
        done
        
        echo "   ✅ 清理完成"
        ;;
        
    "help"|"-h"|"--help")
        echo "📋 ModelCall 任务管理工具"
        echo ""
        echo "用法:"
        echo "  $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  list, ls              列出所有任务"
        echo "  stop <pattern>        停止匹配的任务"
        echo "  stopall              停止所有任务"
        echo "  monitor <pattern>     监控任务日志"
        echo "  status <pattern>      查看任务状态"
        echo "  clean                清理已停止任务的PID文件"
        echo "  help                 显示帮助信息"
        echo ""
        echo "示例:"
        echo "  $0 list                           # 列出所有任务"
        echo "  $0 stop github_code_rating        # 停止GitHub评分任务"
        echo "  $0 monitor en_corpus              # 监控英文语料任务"
        echo "  $0 status distributed_rating      # 查看分布式任务状态"
        ;;
        
    *)
        echo "❌ 未知命令: $COMMAND"
        echo "使用 '$0 help' 查看帮助信息"
        exit 1
        ;;
esac

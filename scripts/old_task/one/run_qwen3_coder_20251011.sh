#!/bin/bash
# =============================================================================
# 快捷启动脚本 - Qwen3-Coder-480B 响应生成 (20251011)
# =============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

bash "$SCRIPT_DIR/run_distillation_task.sh" \
    configs/tasks/data_distillation/20251011/generate_response_qwen3_coder.yaml


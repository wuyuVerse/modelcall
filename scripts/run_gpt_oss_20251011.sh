#!/bin/bash
# =============================================================================
# 快捷启动脚本 - GPT-OSS-120B 响应生成 (20251011)
# =============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

bash "$SCRIPT_DIR/run_distillation_task.sh" \
    configs/tasks/data_distillation/20251011/generate_response_gpt_oss_test.yaml


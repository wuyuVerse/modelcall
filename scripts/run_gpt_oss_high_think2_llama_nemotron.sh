#!/bin/bash
# =============================================================================
# 启动脚本 - GPT-OSS-120B High Think-2 - Llama-Nemotron Chat
# =============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

bash "$SCRIPT_DIR/run_distillation_task.sh" \
    configs/tasks/data_distillation/20251015/generate_response_gpt_oss_llama_nemotron_high_think.yaml



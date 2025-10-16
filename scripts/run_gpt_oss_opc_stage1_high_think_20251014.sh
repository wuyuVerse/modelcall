#!/bin/bash
# =============================================================================
# 快捷启动脚本 - GPT-OSS-120B High Think - OPC Stage1 (20251014)
# =============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

bash "$SCRIPT_DIR/run_distillation_task.sh" \
    configs/tasks/data_distillation/20251014/generate_response_gpt_oss_opc_stage1_high_think.yaml



#!/bin/bash
# =============================================================================
# 快捷启动脚本 - GPT-OSS-120B High Think-2 响应生成 (20251015)
# =============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "===> Llama-Nemotron Chat 数据"
bash "$SCRIPT_DIR/run_distillation_task.sh" \
    configs/tasks/data_distillation/20251015/generate_response_gpt_oss_llama_nemotron_high_think.yaml

echo "\n===> Nemotron v2 数据"
bash "$SCRIPT_DIR/run_distillation_task.sh" \
    configs/tasks/data_distillation/20251015/generate_response_gpt_oss_nemotron_v2_high_think.yaml

echo "\n===> oo1.jsonl 数据"
bash "$SCRIPT_DIR/run_distillation_task.sh" \
    configs/tasks/data_distillation/20251015/generate_response_gpt_oss_oo1_high_think.yaml



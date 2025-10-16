#!/bin/bash
# OpenCoder Stage2 批量蒸馏任务提交脚本（使用配置文件）

set -e

echo "=========================================="
echo "OpenCoder Stage2 批量数据蒸馏任务提交"
echo "=========================================="

# 激活 conda 环境（用于 SiFlow SDK）
echo ""
echo "激活 conda 环境..."
source /volume/pt-train/users/wzhang/miniconda3/bin/activate /volume/pt-train/users/wzhang/miniconda3/envs/wzhang_base

# 切换到项目目录
cd /volume/pt-train/users/wzhang/wjj-workspace/modelcall

# 使用配置文件运行批量提交任务
echo ""
echo "运行批量提交任务..."
python -m modelcall run-task configs/tasks/data_distillation/batch_submit_opc_stage2.yaml

echo ""
echo "=========================================="
echo "任务提交完成!"
echo "=========================================="
echo ""
echo "任务完成后，运行以下命令合并结果："
echo "python -m modelcall run-task configs/tasks/data_distillation/merge_opc_stage2_results.yaml"
echo ""


#!/bin/bash
# 重新处理 OPC Stage1 Qwen3-Coder-480B 错误数据
# 用途：处理之前失败的数据，不使用 retry 模式

set -e

echo "=========================================="
echo "重新处理 OPC Stage1 Qwen3-480B 错误数据"
echo "=========================================="

# 激活虚拟环境
echo ""
echo "激活虚拟环境..."
source /volume/pt-train/users/wzhang/wjj-workspace/modelcall/.venv/bin/activate

# 切换到项目目录
cd /volume/pt-train/users/wzhang/wjj-workspace/modelcall

# 加载环境变量（如果需要）
if [ -f "env/add_siflow.env" ]; then
    export $(cat env/add_siflow.env | grep -v '^#' | xargs)
    echo "✅ 已加载环境变量"
fi

echo ""
echo "任务信息："
echo "  输入文件: OpenCoder-LLM_opc-sft-stage1_error.jsonl (1814条)"
echo "  输出目录: /volume/pt-train/users/wzhang/coder/coder-data/dataset/opc-sft/generated/retry_20251013_qwen3"
echo "  模型配置: qwen3-coder-480b-wzhang"
echo "  并发数: 1024"
echo ""

echo "运行任务..."
python -m modelcall run-task configs/tasks/data_distillation/20251013/retry_opc_stage1_qwen3_480b.yaml

echo ""
echo "=========================================="
echo "任务完成！"
echo "=========================================="


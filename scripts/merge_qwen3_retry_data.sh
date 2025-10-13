#!/bin/bash
# 将 Qwen3 重试数据合并到原始文件中

set -e

echo "=========================================="
echo "合并 Qwen3 重试数据到原始文件"
echo "=========================================="

# 定义文件路径
ORIGINAL_FILE="/volume/pt-train/users/wzhang/coder/coder-data/dataset/opc-sft/generated/opc-sft-stage1_gpt-oss-120b.jsonl"
RETRY_FILE="/volume/pt-train/users/wzhang/coder/coder-data/dataset/opc-sft/generated/retry_20251013/opc-sft-stage1_gpt-oss-120b_error_retry_1.jsonl"
BACKUP_FILE="${ORIGINAL_FILE}.backup_$(date +%Y%m%d_%H%M%S)"

echo "原始文件: $ORIGINAL_FILE"
echo "重试文件: $RETRY_FILE"
echo "备份文件: $BACKUP_FILE"
echo ""

# 检查文件是否存在
if [ ! -f "$ORIGINAL_FILE" ]; then
    echo "❌ 错误: 原始文件不存在: $ORIGINAL_FILE"
    exit 1
fi

if [ ! -f "$RETRY_FILE" ]; then
    echo "❌ 错误: 重试文件不存在: $RETRY_FILE"
    exit 1
fi

# 显示文件统计
ORIGINAL_COUNT=$(wc -l < "$ORIGINAL_FILE")
RETRY_COUNT=$(wc -l < "$RETRY_FILE")

echo "📊 文件统计:"
echo "  原始文件行数: $ORIGINAL_COUNT"
echo "  重试文件行数: $RETRY_COUNT"
echo ""

# 创建备份
echo "🔄 创建原始文件备份..."
cp "$ORIGINAL_FILE" "$BACKUP_FILE"
echo "✅ 备份完成: $BACKUP_FILE"

# 合并文件
echo "🔄 合并重试数据到原始文件..."
cat "$RETRY_FILE" >> "$ORIGINAL_FILE"

# 验证合并结果
NEW_COUNT=$(wc -l < "$ORIGINAL_FILE")
EXPECTED_COUNT=$((ORIGINAL_COUNT + RETRY_COUNT))

echo ""
echo "📊 合并结果:"
echo "  原始行数: $ORIGINAL_COUNT"
echo "  重试行数: $RETRY_COUNT"
echo "  合并后行数: $NEW_COUNT"
echo "  期望行数: $EXPECTED_COUNT"

if [ "$NEW_COUNT" -eq "$EXPECTED_COUNT" ]; then
    echo "✅ 合并成功！数据行数正确。"
else
    echo "❌ 警告: 合并后行数不匹配，请检查！"
    echo "🔄 恢复备份文件..."
    cp "$BACKUP_FILE" "$ORIGINAL_FILE"
    echo "✅ 已恢复原始文件"
    exit 1
fi

echo ""
echo "=========================================="
echo "合并完成！"
echo "原始文件已更新: $ORIGINAL_FILE"
echo "备份文件: $BACKUP_FILE"
echo "=========================================="

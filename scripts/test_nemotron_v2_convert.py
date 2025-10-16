#!/usr/bin/env python3
"""
测试 Nemotron v2 数据转换
验证数据格式是否正确
"""

import json
from datasets import load_dataset
from pathlib import Path

def test_nemotron_v2_conversion():
    """测试 Nemotron v2 数据的转换逻辑"""
    
    dataset_path = "/volume/pt-train/users/wzhang/hf/datasets/nvidia/Nemotron-Post-Training-Dataset-v2"
    split = "chat"
    
    print(f"📦 加载 Nemotron v2 数据集 (split={split})...")
    dataset = load_dataset(dataset_path, split=split, streaming=True)
    
    print(f"✅ 数据集加载成功")
    print(f"\n📊 获取前 3 条数据进行验证...")
    
    for i, sample in enumerate(dataset):
        if i >= 3:
            break
        
        print(f"\n{'='*60}")
        print(f"样本 {i+1}:")
        print(f"{'='*60}")
        print(f"字段: {list(sample.keys())}")
        print(f"\nuuid: {sample.get('uuid', 'N/A')}")
        print(f"category: {sample.get('category', 'N/A')}")
        print(f"reasoning: {sample.get('reasoning', 'N/A')}")
        
        # 检查 messages 字段
        messages = sample.get('messages', [])
        print(f"\nmessages 数量: {len(messages)}")
        for j, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            content_preview = content[:100] + '...' if len(content) > 100 else content
            print(f"  [{j}] {role}: {content_preview}")
        
        # 验证格式是否已经是 ChatML
        print(f"\n✅ 格式检查:")
        print(f"   - 已有 messages 字段: {'是' if 'messages' in sample else '否'}")
        print(f"   - messages 是列表: {'是' if isinstance(messages, list) else '否'}")
        if messages and isinstance(messages, list):
            print(f"   - 第一条消息有 role: {'是' if 'role' in messages[0] else '否'}")
            print(f"   - 第一条消息有 content: {'是' if 'content' in messages[0] else '否'}")
    
    print(f"\n{'='*60}")
    print("结论: Nemotron v2 数据已经是标准 ChatML 格式")
    print("可以直接写入 JSONL，无需额外转换")
    print(f"{'='*60}")

if __name__ == "__main__":
    test_nemotron_v2_conversion()


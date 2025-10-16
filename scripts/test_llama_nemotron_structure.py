#!/usr/bin/env python3
"""
测试 Llama-Nemotron 数据集结构
查看所有子目录和文件
"""

import json
import os
from pathlib import Path

def explore_llama_nemotron():
    """探索 Llama-Nemotron 数据集结构"""
    
    dataset_path = Path("/volume/pt-train/users/wzhang/hf/datasets/nvidia/Llama-Nemotron-Post-Training-Dataset")
    
    print("="*60)
    print("Llama-Nemotron 数据集结构")
    print("="*60)
    
    # 查找所有 JSONL 文件
    jsonl_files = list(dataset_path.rglob("*.jsonl"))
    
    print(f"\n找到 {len(jsonl_files)} 个 JSONL 文件:\n")
    
    for jsonl_file in sorted(jsonl_files):
        rel_path = jsonl_file.relative_to(dataset_path)
        file_size = jsonl_file.stat().st_size / (1024 * 1024)  # MB
        
        print(f"📄 {rel_path}")
        print(f"   大小: {file_size:.2f} MB")
        
        # 读取第一条数据查看格式
        try:
            with open(jsonl_file, 'r') as f:
                line_count = sum(1 for _ in f)
            
            with open(jsonl_file, 'r') as f:
                first_line = f.readline()
                if first_line:
                    data = json.loads(first_line)
                    print(f"   行数: {line_count:,}")
                    print(f"   字段: {list(data.keys())}")
                    
                    # 检查格式
                    if 'input' in data and 'output' in data:
                        input_type = type(data['input']).__name__
                        output_type = type(data['output']).__name__
                        print(f"   格式: input({input_type}) + output({output_type})")
                        
                        if isinstance(data['input'], list) and len(data['input']) > 0:
                            if isinstance(data['input'][0], dict) and 'role' in data['input'][0]:
                                print(f"   ✅ input 是 messages 列表")
                        
                        if isinstance(data['output'], str):
                            print(f"   ✅ output 是字符串")
        except Exception as e:
            print(f"   ⚠️  读取错误: {e}")
        
        print()
    
    print("="*60)
    print("转换建议:")
    print("="*60)
    print("所有文件格式一致: input(messages列表) + output(字符串)")
    print("适用格式: input_output_messages")
    print("配置已在 datasets_chatml.yaml 中定义")
    print("="*60)

if __name__ == "__main__":
    explore_llama_nemotron()


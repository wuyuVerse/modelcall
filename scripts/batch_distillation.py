#!/usr/bin/env python3
"""批量数据蒸馏主控脚本 - 完整流程管理"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict
import yaml

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from scripts.jsonl_split_merge import split_jsonl, merge_jsonl
from scripts.siflow_batch_submit import generate_distillation_cmds, batch_submit_tasks


def load_model_config(model_config_path: str) -> Dict:
    """加载模型配置文件"""
    config_path = Path(model_config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"模型配置文件不存在: {model_config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        if config_path.suffix == '.yaml' or config_path.suffix == '.yml':
            return yaml.safe_load(f)
        elif config_path.suffix == '.json':
            return json.load(f)
        else:
            raise ValueError(f"不支持的配置文件格式: {config_path.suffix}")


def generate_response_generation_cmds(
    split_dir: str,
    output_base_dir: str,
    model_config: str,
    concurrency: int = 30,
    batch_size: int = 30,
    retry_mode: bool = False,
    resume_mode: bool = True
) -> List[str]:
    """为切分后的文件生成响应生成命令"""
    split_path = Path(split_dir)
    split_files = sorted(list(split_path.glob("*_split_*.jsonl")))
    
    if not split_files:
        raise ValueError(f"在 {split_dir} 中没有找到切分文件")
    
    print(f"找到 {len(split_files)} 个切分文件")
    
    # 读取模型配置以确定输出子目录名称
    try:
        config = load_model_config(model_config)
        model_name = config.get('chat_config', {}).get('model', 'unknown')
        # 简化模型名称作为目录名
        model_dir_name = model_name.replace('/', '_').replace('-', '_')
    except Exception as e:
        print(f"警告: 无法读取模型配置，使用默认目录名: {e}")
        model_dir_name = Path(model_config).stem
    
    cmds = []
    for split_file in split_files:
        # 为每个分片创建独立的输出目录
        split_name = split_file.stem  # e.g., "OpenCoder-LLM_opc-sft-stage2_split_0001"
        output_dir = Path(output_base_dir) / model_dir_name / split_name
        
        retry_flag = "--retry" if retry_mode else ""
        resume_flag = "--no-resume" if not resume_mode else ""
        
        cmd = f"""
#!/bin/bash
set -e

# 切换到项目目录
cd /volume/pt-train/users/wzhang/wjj-workspace/modelcall

# 定义变量
INPUT_PATH="{split_file}"
OUTPUT_PATH="{output_dir}"
MODEL_CONFIG="{model_config}"
VENV_PYTHON="/volume/pt-train/users/wzhang/wjj-workspace/modelcall/.venv/bin/python"

# 运行响应生成（使用虚拟环境中的 python）
$VENV_PYTHON scripts/run_response_generation.py \\
    --input-path "$INPUT_PATH" \\
    --output-path "$OUTPUT_PATH" \\
    --model-config "$MODEL_CONFIG" \\
    --concurrency {concurrency} \\
    --batch-size {batch_size} \\
    {retry_flag} {resume_flag}
""".strip()
        
        cmds.append(cmd)
    
    return cmds


def step1_split_file(input_file: str, num_chunks: int):
    """步骤1: 切分文件"""
    print("\n" + "=" * 80)
    print("步骤 1/4: 切分文件")
    print("=" * 80)
    
    split_dir = split_jsonl(input_file=input_file, num_chunks=num_chunks)
    print(f"\n✅ 文件切分完成: {split_dir}")
    
    return split_dir


def step2_submit_tasks(
    split_dir: str,
    output_base_dir: str,
    model_configs: List[str],
    name_prefix: str,
    concurrency: int,
    batch_size: int,
    count_per_pod: int,
    priority: str,
    guarantee: bool,
    region: str,
    cluster: str,
    dry_run: bool = False
):
    """步骤2: 提交任务到 SiFlow"""
    print("\n" + "=" * 80)
    print("步骤 2/4: 批量提交任务")
    print("=" * 80)
    
    all_results = []
    
    for model_config in model_configs:
        model_name = Path(model_config).stem
        task_prefix = f"{name_prefix}-{model_name}"
        
        print(f"\n处理模型: {model_name}")
        print(f"配置文件: {model_config}")
        print(f"任务前缀: {task_prefix}")
        
        # 生成命令
        cmds = generate_response_generation_cmds(
            split_dir=split_dir,
            output_base_dir=output_base_dir,
            model_config=model_config,
            concurrency=concurrency,
            batch_size=batch_size
        )
        
        print(f"生成了 {len(cmds)} 个任务命令")
        
        if dry_run:
            print(f"\n【Dry Run】命令预览（前3个）：")
            for i, cmd in enumerate(cmds[:3], 1):
                print(f"\n任务 {i}:")
                print(cmd)
            continue
        
        # 提交任务
        results = batch_submit_tasks(
            cmds=cmds,
            name_prefix=task_prefix,
            region=region,
            cluster=cluster,
            count_per_pod=count_per_pod,
            guarantee=guarantee,
            priority=priority
        )
        
        all_results.extend(results)
        
        # 统计
        success_count = sum(1 for r in results if r["success"])
        print(f"\n模型 {model_name}: 提交 {len(results)} 个任务, 成功 {success_count} 个")
    
    if not dry_run:
        total_success = sum(1 for r in all_results if r["success"])
        print(f"\n✅ 总共提交 {len(all_results)} 个任务, 成功 {total_success} 个")
    
    return all_results


def step3_wait_and_merge(split_dir: str, output_base_dir: str, model_configs: List[str]):
    """步骤3&4: 等待完成并合并结果"""
    print("\n" + "=" * 80)
    print("步骤 3/4: 等待任务完成")
    print("=" * 80)
    print("请在 SiFlow 控制台监控任务执行状态")
    print("任务完成后，运行以下命令合并结果：")
    
    for model_config in model_configs:
        try:
            config = load_model_config(model_config)
            model_name = config.get('chat_config', {}).get('model', 'unknown')
            model_dir_name = model_name.replace('/', '_').replace('-', '_')
        except Exception:
            model_dir_name = Path(model_config).stem
        
        merge_input_dir = Path(output_base_dir) / model_dir_name
        merge_output_file = Path(output_base_dir) / f"{model_dir_name}_merged.jsonl"
        
        print(f"\n# 合并 {model_dir_name} 的结果:")
        print(f"python scripts/merge_split_results.py \\")
        print(f"    --input-dir {merge_input_dir} \\")
        print(f"    --output-file {merge_output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="批量数据蒸馏主控脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:

1. 完整流程（切分 + 提交）:
   python scripts/batch_distillation.py \\
       --input-file /path/to/data.jsonl \\
       --output-dir /path/to/output \\
       --model-configs configs/models/claude-sonnet-4.5-thinking.yaml \\
                       configs/models/claude-sonnet-4.5.yaml \\
       --num-chunks 1000 \\
       --concurrency 30

2. 只切分文件:
   python scripts/batch_distillation.py split \\
       --input-file /path/to/data.jsonl \\
       --num-chunks 1000

3. 只提交任务（假设已经切分）:
   python scripts/batch_distillation.py submit \\
       --split-dir /path/to/splits \\
       --output-dir /path/to/output \\
       --model-configs configs/models/claude-sonnet-4.5-thinking.yaml
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 完整流程
    full_parser = subparsers.add_parser("full", help="完整流程（切分 + 提交）")
    full_parser.add_argument("--input-file", "-i", required=True, help="输入 JSONL 文件")
    full_parser.add_argument("--output-dir", "-o", required=True, help="输出基础目录")
    full_parser.add_argument("--model-configs", "-m", nargs="+", required=True, help="模型配置文件列表")
    full_parser.add_argument("--num-chunks", "-n", type=int, required=True, help="切分成多少份")
    full_parser.add_argument("--name-prefix", default="distill", help="任务名称前缀")
    full_parser.add_argument("--concurrency", "-c", type=int, default=30, help="每个任务的并发数")
    full_parser.add_argument("--batch-size", "-b", type=int, default=30, help="批量保存大小")
    full_parser.add_argument("--count-per-pod", type=int, default=48, help="每个 pod 的 CPU 核心数")
    full_parser.add_argument("--priority", choices=["low", "medium", "high"], default="medium")
    full_parser.add_argument("--guarantee", action="store_true", help="是否保证资源")
    full_parser.add_argument("--region", default="cn-beijing")
    full_parser.add_argument("--cluster", default="auriga")
    full_parser.add_argument("--dry-run", action="store_true", help="只生成命令不提交")
    
    # 只切分
    split_parser = subparsers.add_parser("split", help="只切分文件")
    split_parser.add_argument("--input-file", "-i", required=True, help="输入 JSONL 文件")
    split_parser.add_argument("--num-chunks", "-n", type=int, required=True, help="切分成多少份")
    
    # 只提交
    submit_parser = subparsers.add_parser("submit", help="只提交任务（假设已切分）")
    submit_parser.add_argument("--split-dir", "-i", required=True, help="切分文件目录")
    submit_parser.add_argument("--output-dir", "-o", required=True, help="输出基础目录")
    submit_parser.add_argument("--model-configs", "-m", nargs="+", required=True, help="模型配置文件列表")
    submit_parser.add_argument("--name-prefix", default="distill", help="任务名称前缀")
    submit_parser.add_argument("--concurrency", "-c", type=int, default=30, help="每个任务的并发数")
    submit_parser.add_argument("--batch-size", "-b", type=int, default=30, help="批量保存大小")
    submit_parser.add_argument("--count-per-pod", type=int, default=48, help="每个 pod 的 CPU 核心数")
    submit_parser.add_argument("--priority", choices=["low", "medium", "high"], default="medium")
    submit_parser.add_argument("--guarantee", action="store_true", help="是否保证资源")
    submit_parser.add_argument("--region", default="cn-beijing")
    submit_parser.add_argument("--cluster", default="auriga")
    submit_parser.add_argument("--dry-run", action="store_true", help="只生成命令不提交")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 执行对应的流程
    if args.command == "split":
        step1_split_file(args.input_file, args.num_chunks)
    
    elif args.command == "submit":
        step2_submit_tasks(
            split_dir=args.split_dir,
            output_base_dir=args.output_dir,
            model_configs=args.model_configs,
            name_prefix=args.name_prefix,
            concurrency=args.concurrency,
            batch_size=args.batch_size,
            count_per_pod=args.count_per_pod,
            priority=args.priority,
            guarantee=args.guarantee,
            region=args.region,
            cluster=args.cluster,
            dry_run=args.dry_run
        )
    
    elif args.command == "full":
        # 步骤1: 切分
        split_dir = step1_split_file(args.input_file, args.num_chunks)
        
        # 步骤2: 提交
        step2_submit_tasks(
            split_dir=split_dir,
            output_base_dir=args.output_dir,
            model_configs=args.model_configs,
            name_prefix=args.name_prefix,
            concurrency=args.concurrency,
            batch_size=args.batch_size,
            count_per_pod=args.count_per_pod,
            priority=args.priority,
            guarantee=args.guarantee,
            region=args.region,
            cluster=args.cluster,
            dry_run=args.dry_run
        )
        
        # 步骤3&4: 提示合并命令
        if not args.dry_run:
            step3_wait_and_merge(split_dir, args.output_dir, args.model_configs)


if __name__ == "__main__":
    main()


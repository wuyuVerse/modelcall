#!/usr/bin/env python3
"""
任务配置文件生成器
"""

import argparse
import yaml
from pathlib import Path


def create_task_config(task_name: str, template: str = "basic") -> dict:
    """创建任务配置"""
    
    templates = {
        "basic": {
            "task_name": task_name,
            "description": f"{task_name} 任务",
            "data": {
                "input_folder": "path/to/input",
                "output_folder": f"path/to/output/{task_name}/" + "{timestamp}",
                "stat_folder": f"./data/stats/{task_name}",
                "input_key": "text",
                "prompt_format_key": "text"
            },
            "model": {
                "config_path": "configs/models/dpsk-v3-0526.yaml"
            },
            "prompt": {
                "config_path": "configs/prompts/en_corpus_rating_v0.1.yaml"
            },
            "concurrency": {
                "max_concurrent_files": 2,
                "max_concurrent_requests": 10,
                "chunk_size": 100,
                "parquet_save_interval": 200
            },
            "distributed": {
                "enabled": False,
                "world_size": 1
            },
            "debug": {
                "enabled": False,
                "max_files": None,
                "max_items_per_file": None
            },
            "retry": {
                "enable_format_validation_retry": True,
                "max_retries": 3
            },
            "options": {
                "resume": True,
                "delete_existing": False
            }
        },
        
        "distributed": {
            "task_name": task_name,
            "description": f"{task_name} 分布式任务",
            "data": {
                "input_folder": "path/to/input",
                "output_folder": f"path/to/output/{task_name}/" + "{timestamp}_run_{run_index}",
                "stat_folder": f"./data/stats/{task_name}",
                "input_key": "content_truncate_32k",
                "prompt_format_key": "text"
            },
            "model": {
                "config_path": "configs/models/dpsk-v3-0526.yaml"
            },
            "prompt": {
                "config_path": "configs/prompts/en_corpus_rating_v0.1.yaml"
            },
            "concurrency": {
                "max_concurrent_files": 1,
                "max_concurrent_requests": 512,
                "chunk_size": 1024,
                "parquet_save_interval": 1024
            },
            "distributed": {
                "enabled": True,
                "world_size": 10,
                "num_runs": 3
            },
            "debug": {
                "enabled": False,
                "max_files": None,
                "max_items_per_file": None
            },
            "retry": {
                "enable_format_validation_retry": True,
                "max_retries": 3
            },
            "options": {
                "resume": True,
                "delete_existing": False
            },
            "environment": {
                "api_provider": "local",
                "timeout": 300
            }
        }
    }
    
    return templates.get(template, templates["basic"])


def main():
    parser = argparse.ArgumentParser(description="创建任务配置文件")
    parser.add_argument("task_name", help="任务名称")
    parser.add_argument("--template", choices=["basic", "distributed"], default="basic", help="配置模板")
    parser.add_argument("--output", help="输出文件路径 (默认: configs/tasks/{task_name}.yaml)")
    
    args = parser.parse_args()
    
    # 生成配置
    config = create_task_config(args.task_name, args.template)
    
    # 确定输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(f"configs/tasks/{args.task_name}.yaml")
    
    # 确保目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 保存配置
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
    
    print(f"✅ 任务配置已创建: {output_path}")
    print(f"📋 任务名称: {args.task_name}")
    print(f"🏷️  模板类型: {args.template}")
    print(f"\n🚀 运行任务:")
    print(f"   ./scripts/run_task.sh {output_path}")


if __name__ == "__main__":
    main()

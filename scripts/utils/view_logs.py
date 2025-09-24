#!/usr/bin/env python3
"""
日志查看工具
"""

import argparse
import json
import os
from pathlib import Path
from datetime import datetime

import pandas as pd
from prettytable import PrettyTable


def view_task_logs(log_dir: str, task_name: str = None):
    """查看任务日志"""
    log_path = Path(log_dir)
    
    if not log_path.exists():
        print(f"❌ 日志目录不存在: {log_dir}")
        return
    
    # 查找日志文件
    if task_name:
        log_files = list(log_path.glob(f"{task_name}_*.log"))
    else:
        log_files = list(log_path.glob("*.log"))
    
    if not log_files:
        print(f"❌ 未找到日志文件")
        return
    
    print(f"📋 找到 {len(log_files)} 个日志文件:")
    
    table = PrettyTable(['文件名', '大小', '修改时间'])
    
    for log_file in sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True):
        size = log_file.stat().st_size
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        
        table.add_row([
            log_file.name,
            f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/(1024*1024):.1f}MB",
            mtime.strftime("%Y-%m-%d %H:%M:%S")
        ])
    
    print(table)


def view_batch_details(log_dir: str, task_name: str):
    """查看批量处理详情"""
    log_path = Path(log_dir)
    batch_file = log_path / f"{task_name}_batch_details.jsonl"
    
    if not batch_file.exists():
        print(f"❌ 批量日志文件不存在: {batch_file}")
        return
    
    print(f"📊 读取批量处理详情: {batch_file}")
    
    # 读取批量日志
    batch_data = []
    with open(batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                batch_data.append(json.loads(line))
    
    if not batch_data:
        print("❌ 批量日志为空")
        return
    
    # 统计信息
    df = pd.DataFrame(batch_data)
    
    print(f"📈 批量处理统计:")
    print(f"   总记录数: {len(df):,}")
    print(f"   时间范围: {df['timestamp'].min()} - {df['timestamp'].max()}")
    
    # 状态分布
    if 'status' in df.columns:
        status_counts = df['status'].value_counts()
        print(f"\n📊 状态分布:")
        for status, count in status_counts.items():
            percentage = count / len(df) * 100
            print(f"   {status}: {count:,} ({percentage:.1f}%)")
    
    # 评分分布
    if 'score' in df.columns:
        scores = df['score'].dropna()
        if len(scores) > 0:
            print(f"\n⭐ 评分统计:")
            print(f"   平均分: {scores.mean():.2f}")
            print(f"   中位数: {scores.median():.2f}")
            print(f"   分数范围: {scores.min():.0f} - {scores.max():.0f}")
    
    # 文件分布
    if 'file' in df.columns:
        file_counts = df['file'].value_counts()
        print(f"\n📁 文件处理分布 (Top 10):")
        for file_name, count in file_counts.head(10).items():
            print(f"   {file_name}: {count:,}")


def view_final_stats(log_dir: str, task_name: str):
    """查看最终统计"""
    log_path = Path(log_dir)
    stats_file = log_path / f"{task_name}_final_stats.json"
    
    if not stats_file.exists():
        print(f"❌ 最终统计文件不存在: {stats_file}")
        return
    
    with open(stats_file, 'r', encoding='utf-8') as f:
        stats = json.load(f)
    
    print(f"🎯 最终统计 - {stats['task_name']}")
    print(f"   完成时间: {stats['completion_time']}")
    
    if stats.get('world_size', 1) > 1:
        print(f"   作业配置: Job {stats['job_index']}/{stats['world_size']}")
    
    stat_data = stats['stats']
    
    print(f"\n📊 处理统计:")
    print(f"   文件: {stat_data['processed_files']}/{stat_data['total_files']}")
    print(f"   项目: {stat_data['processed_items']:,}/{stat_data['total_items']:,}")
    print(f"   成功率: {stat_data['success_rate']:.1f}%")
    print(f"   处理速度: {stat_data['processing_speed']:.1f} 项/分钟")
    print(f"   总用时: {stat_data['elapsed_time']:.1f} 秒")


def main():
    parser = argparse.ArgumentParser(description="查看ModelCall任务日志")
    parser.add_argument("--log_dir", default="./logs", help="日志目录")
    parser.add_argument("--task", help="任务名称")
    parser.add_argument("--details", action="store_true", help="查看批量处理详情")
    parser.add_argument("--stats", action="store_true", help="查看最终统计")
    
    args = parser.parse_args()
    
    if args.details:
        if not args.task:
            print("❌ 查看详情需要指定任务名称 (--task)")
            return
        view_batch_details(args.log_dir, args.task)
    elif args.stats:
        if not args.task:
            print("❌ 查看统计需要指定任务名称 (--task)")
            return
        view_final_stats(args.log_dir, args.task)
    else:
        view_task_logs(args.log_dir, args.task)


if __name__ == "__main__":
    main()

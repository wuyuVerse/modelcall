"""Base classes for data preprocessing."""

from __future__ import annotations

import os
import json
import copy
import argparse
from uuid import uuid4
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

import tiktoken
import pandas as pd

from ..common.utils import DEFAULT_FILE_STAT, save_progress_stat, load_progress_stat, get_filesystem, process_text
from ..common.data_io import DataReader, DataWriter


class BasePreprocessor:
    """Base class for data preprocessing."""
    
    def __init__(self, 
                 raw_path: str,
                 output_dir: str,
                 stat_dir: str,
                 fs_cfg: Dict[str, Any],
                 max_tokens: int = 32768,
                 num_proc: int = 32,
                 batch_size: int = 1000):
        self.raw_path = raw_path
        self.output_dir = output_dir
        self.stat_dir = stat_dir
        self.fs_cfg = fs_cfg
        self.max_tokens = max_tokens
        self.num_proc = num_proc
        self.batch_size = batch_size  # 新增批次大小参数
        self.enc = tiktoken.encoding_for_model("gpt-4o")
        
        # Ensure stat directory exists
        os.makedirs(stat_dir, exist_ok=True)
    
    def get_file_list(self) -> List[Tuple[str, str]]:
        """Get list of (input_path, output_path) tuples to process."""
        raise NotImplementedError
    
    def process_single_file(self, input_path: str, output_path: str) -> Tuple[bool, int]:
        """Process a single file. Returns (success, n_samples)."""
        try:
            fs = get_filesystem(input_path, self.fs_cfg)
            reader = DataReader(fs)
            writer = DataWriter(fs)
            
            # Read data
            data = list(reader.read(input_path))
            
            # Process data with batch writing
            return self.process_data_with_batching(data, output_path, writer)
            
        except Exception as e:
            print(f"Failed to process file {input_path}: {e}")
            return False, 0
    
    def process_data_with_batching(self, data: List[Dict[str, Any]], output_path: str, writer: DataWriter) -> Tuple[bool, int]:
        """Process data with batch writing support and proper resume logic."""
        from datetime import datetime
        
        # 创建进度文件路径（避免多进程冲突）
        progress_file = output_path + ".progress.json"
        
        # 检查断点续传状态
        existing_data = []
        start_index = 0
        
        if os.path.exists(output_path) and os.path.exists(progress_file):
            try:
                # 读取进度信息
                with open(progress_file, 'r', encoding='utf-8') as f:
                    progress_info = json.load(f)
                
                start_index = progress_info.get('processed_count', 0)
                
                # 读取已有数据
                temp_fs = get_filesystem(output_path, self.fs_cfg)
                temp_reader = DataReader(temp_fs)
                existing_data = list(temp_reader.read(output_path))
                
                print(f"📊 断点续传: 跳过前 {start_index} 个items, 已有 {len(existing_data)} 条记录")
                
                # 验证数据一致性
                if len(existing_data) != start_index:
                    print(f"⚠️ 数据不一致，重新开始处理")
                    start_index = 0
                    existing_data = []
                    
            except Exception as e:
                print(f"⚠️ 无法读取断点续传数据: {e}, 从头开始")
                start_index = 0
                existing_data = []
        
        processed_data = list(existing_data)
        items_since_last_save = 0
        
        # 处理剩余数据
        for i in range(start_index, len(data)):
            processed_item = self.process_item(data[i])
            if processed_item:
                processed_data.append(processed_item)
                items_since_last_save += 1
            
            # 按批次保存
            if items_since_last_save >= self.batch_size or i == len(data) - 1:
                # 写入数据文件
                writer.write(output_path, processed_data)
                
                # 更新进度文件
                progress_info = {
                    "processed_count": i + 1,
                    "total_items": len(processed_data),
                    "last_update": datetime.now().isoformat(),
                    "batch_size": self.batch_size
                }
                
                with open(progress_file, 'w', encoding='utf-8') as f:
                    json.dump(progress_info, f, indent=2)
                
                print(f"💾 批次保存: 处理到第 {i+1}/{len(data)} 项, 总计 {len(processed_data)} 条记录")
                items_since_last_save = 0
        
        # 完成后清理进度文件
        if os.path.exists(progress_file):
            os.remove(progress_file)
            
        return True, len(processed_data)
    
    def process_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single data item. Override in subclasses."""
        # Default processing: add ID if missing and truncate text
        result = copy.deepcopy(item)
        
        # Add ID if missing
        if 'id' not in result:
            result['id'] = str(uuid4())
        
        # Process text content
        text_field = self.get_text_field(result)
        if text_field and text_field in result:
            processed_text = process_text(result[text_field], self.enc, self.max_tokens)
            result[f'{text_field}_truncate_{self.max_tokens//1024}k'] = processed_text
        
        return result
    
    def get_text_field(self, item: Dict[str, Any]) -> Optional[str]:
        """Get the name of the text field to process. Override in subclasses."""
        # Try common text field names
        for field in ['text', 'content', 'body']:
            if field in item:
                return field
        return None
    
    def check_existing_progress(self, file_pairs: List[Tuple[str, str]]) -> List[Tuple[str, str, str]]:
        """Check existing progress and return files that need processing."""
        files_to_process = []
        n_completed = 0
        n_partial = 0
        n_no_stat = 0
        
        for input_file, output_file in file_pairs:
            # Create progress stat file path
            rel_path = input_file.split(self.raw_path)[-1].lstrip("/")
            progress_stat_file = os.path.join(self.stat_dir, rel_path + ".json")
            
            # Check if already processed
            stat = load_progress_stat(progress_stat_file)
            if stat and stat.get("formatted_file_path") and stat.get("processing_complete", False):
                # 检查输出文件是否真实存在
                output_fs = get_filesystem(output_file, self.fs_cfg)
                try:
                    if output_fs.exists(output_file):
                        n_completed += 1
                        print(f"✓ Skipping completed file: {os.path.basename(input_file)}")
                        continue
                except:
                    pass
            
            # 检查是否有部分处理结果
            if stat and stat.get("formatted_file_path"):
                n_partial += 1
                print(f"⚡ Found partial progress for: {os.path.basename(input_file)}")
            else:
                n_no_stat += 1
            
            files_to_process.append((input_file, output_file, progress_stat_file))
        
        print(f"Progress check: {n_completed} completed, {n_partial} partial, {n_no_stat} new files to process")
        return files_to_process
    
    def process_worker(self, args_tuple: Tuple[str, str, str]) -> Tuple[str, bool]:
        """Worker function for multiprocessing."""
        input_file, output_file, progress_stat_file = args_tuple
        
        # 记录开始时间
        from datetime import datetime
        start_time = datetime.now()
        
        success, n_sample = self.process_single_file(input_file, output_file)
        
        # 记录结束时间
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # Save enhanced progress statistics
        stat = copy.deepcopy(DEFAULT_FILE_STAT)
        stat["raw_file_path"] = input_file
        stat["formatted_file_path"] = output_file if success else ""
        stat["n_sample"] = n_sample
        stat["processing_complete"] = success
        stat["start_time"] = start_time.isoformat()
        stat["end_time"] = end_time.isoformat()
        stat["processing_time_seconds"] = processing_time
        stat["batch_size"] = self.batch_size
        stat["max_tokens"] = self.max_tokens
        
        # 添加文件信息
        try:
            file_size = os.path.getsize(input_file) if os.path.exists(input_file) else 0
            stat["input_file_size_bytes"] = file_size
        except:
            stat["input_file_size_bytes"] = 0
            
        # 添加输出文件信息
        if success:
            try:
                output_fs = get_filesystem(output_file, self.fs_cfg)
                if output_fs.exists(output_file):
                    stat["output_file_exists"] = True
                    # 对于本地文件，可以获取大小
                    if not output_file.startswith("tos://"):
                        stat["output_file_size_bytes"] = os.path.getsize(output_file)
                else:
                    stat["output_file_exists"] = False
            except Exception as e:
                stat["output_file_exists"] = False
                stat["output_check_error"] = str(e)
        
        save_progress_stat(progress_stat_file, stat)
        
        return input_file, success
    
    def run(self) -> None:
        """Run the preprocessing pipeline."""
        # Get file list
        file_pairs = self.get_file_list()
        print(f"Found {len(file_pairs)} files to process")
        
        # Check existing progress
        files_to_process = self.check_existing_progress(file_pairs)
        
        if not files_to_process:
            print("All files already processed!")
            return
        
        # Process files with multiprocessing
        n_success = 0
        n_fail = 0
        
        with ProcessPoolExecutor(max_workers=self.num_proc) as executor:
            futures = [executor.submit(self.process_worker, args_tuple) 
                      for args_tuple in files_to_process]
            
            with tqdm(total=len(futures), desc="Processing files") as pbar:
                for future in as_completed(futures):
                    input_file, success = future.result()
                    if success:
                        n_success += 1
                    else:
                        n_fail += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({"Success": n_success, "Fail": n_fail})
        
        print(f"Processing complete: {n_success} success, {n_fail} failed")


def create_base_parser() -> argparse.ArgumentParser:
    """Create base argument parser for preprocessing scripts."""
    parser = argparse.ArgumentParser(description="Data preprocessing")
    parser.add_argument("--raw_path", type=str, required=True,
                       help="Path to raw data")
    parser.add_argument("--output_dir", type=str, required=True,
                       help="Output directory for processed data")
    parser.add_argument("--stat_dir", type=str, required=True,
                       help="Directory for progress statistics")
    parser.add_argument("--num_proc", type=int, default=32,
                       help="Number of processes")
    parser.add_argument("--max_tokens", type=int, default=32768,
                       help="Maximum tokens per sample")
    parser.add_argument("--num_files", type=int, default=-1,
                       help="Number of files to process (-1 for all)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed")
    return parser


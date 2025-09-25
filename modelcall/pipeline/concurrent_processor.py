"""Concurrent file processor with two-level concurrency control."""

from __future__ import annotations

import os
import json
import copy
import asyncio
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from uuid import uuid4

from tqdm.asyncio import tqdm
import pandas as pd

from ..utils import get_filesystem, save_progress_stat, load_progress_stat, DEFAULT_FILE_STAT
from ..data_io import DataReader, DataWriter
from .api_scorer import APIScorer, ConcurrentAPIScorer
from ..logging_manager import get_logger


class ConcurrentFileProcessor:
    """Concurrent file processor with two-level semaphore control."""
    
    def __init__(self,
                 input_folder: str,
                 output_folder: str,
                 stat_folder: Optional[str],
                 model_config_path: str,
                 prompt_config_path: str,
                 fs_cfg: Dict[str, Any],
                 max_concurrent_files: int = 2,
                 max_concurrent_requests: int = 10,
                 chunk_size: int = 100,
                 parquet_save_interval: int = -1,
                 input_key: str = "text",
                 prompt_format_key: str = "code_corpus_description_and_sample",
                 enable_format_validation_retry: bool = True):
        
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.stat_folder = stat_folder
        self.fs_cfg = fs_cfg
        self.chunk_size = chunk_size
        self.parquet_save_interval = parquet_save_interval
        self.input_key = input_key
        self.prompt_format_key = prompt_format_key
        
        # Initialize filesystems
        self.input_fs = get_filesystem(input_folder, fs_cfg)
        self.output_fs = get_filesystem(output_folder, fs_cfg)
        
        # Get timeout from environment or default
        request_timeout = int(os.environ.get("REQUEST_TIMEOUT", "120"))
        
        # Initialize API scorer
        self.api_scorer = APIScorer(
            model_config_path=model_config_path,
            prompt_config_path=prompt_config_path,
            max_concurrent_requests=max_concurrent_requests,
            request_timeout=request_timeout,
            enable_format_validation_retry=enable_format_validation_retry
        )
        self.concurrent_scorer = ConcurrentAPIScorer(self.api_scorer)
        
        # Concurrency control
        self.file_semaphore = asyncio.Semaphore(max_concurrent_files)
        
        # Output schema
        self.output_schema = {
            'id': str,
            'text': str,
            'api_status': str,
            'api_fail_reason': str,
            'api_return': str,
            'score': int,
        }
        
        # Add prompt config output schema
        output_config = self.api_scorer.prompt_config.output_config.get("json_default_values", {})
        for key, value in output_config.items():
            self.output_schema[key] = type(value)
    
    def get_files_to_process(self, debug_files: Optional[int] = None, job_index: int = 0, world_size: int = 1) -> List[str]:
        """Get list of files to process with distributed processing support."""
        # 获取输入文件，支持多种格式但输出强制Parquet
        input_patterns = [f"{self.input_folder}/*.parquet", f"{self.input_folder}/*.jsonl"]
        files = []
        for pattern in input_patterns:
            try:
                pattern_files = self.input_fs.glob(pattern)
                files.extend(pattern_files)
            except Exception:
                pass  # 忽略不支持的格式
        files = sorted(files)
        
        # Handle TOS paths
        if self.input_folder.startswith("tos://") and files and not files[0].startswith("tos://"):
            files = [f"tos://{fp}" for fp in files]
        
        # Apply distributed processing file sharding
        if world_size > 1:
            import math
            total_files = len(files)
            chunk_size = math.ceil(total_files / world_size)
            start_index = job_index * chunk_size
            end_index = min(start_index + chunk_size, total_files)
            files = files[start_index:end_index]
            print(f"🌐 分布式处理: Job {job_index}/{world_size}, 处理文件 {start_index}-{end_index-1} (共{len(files)}个)")
        
        if debug_files:
            files = files[:debug_files]
        
        return files
    
    async def process_single_file(self,
                                input_path: str,
                                output_path: str,
                                resume: bool = True,
                                debug_items: Optional[int] = None) -> None:
        """Process a single file with API scoring."""
        
        logger = get_logger()
        filename = os.path.basename(input_path)
        
        async with self.file_semaphore:
            if logger:
                logger.info(f"🟢 开始处理文件: {filename}")
            
            try:
                # Read source data
                reader = DataReader(self.input_fs)
                src_data = list(reader.read(input_path))
                
                if not src_data:
                    if logger:
                        logger.warning(f"跳过文件 {filename}: 未找到数据")
                    return
                
                # Check for duplicate IDs
                all_ids = [item.get('id') for item in src_data]
                if len(set(all_ids)) != len(all_ids):
                    if logger:
                        logger.warning(f"发现重复ID: {filename}")
                
                # Ensure all items have IDs
                for item in src_data:
                    if 'id' not in item or not item['id']:
                        item['id'] = str(uuid4())
                
                # Validate input key exists
                if self.input_key not in src_data[0]:
                    available_keys = list(src_data[0].keys())
                    raise KeyError(f"Input key '{self.input_key}' not found. Available: {available_keys}")
                
                # Update total items count
                if logger:
                    logger.increment_stats(total_items=len(src_data))
                
                # Handle resuming from previous runs
                processed_items = []
                successful_ids = set()
                
                if resume and self.output_fs.exists(output_path):
                    if logger:
                        logger.info(f"📄 从现有输出文件恢复: {filename}")
                    
                    try:
                        reader_out = DataReader(self.output_fs)
                        out_data = list(reader_out.read(output_path))
                        
                        for item in out_data:
                            if item.get("api_status") == "success":
                                successful_ids.add(item['id'])
                        
                        processed_items = [item for item in out_data if item['id'] in successful_ids]
                    except Exception as e:
                        if logger:
                            logger.error(f"读取现有输出文件错误: {e}")
                
                if logger and processed_items:
                    logger.info(f"已加载 {len(processed_items)} 个先前处理的项目")
                
                # Prepare items for processing
                work_items = []
                
                for item in src_data:
                    if item['id'] in successful_ids:
                        continue
                    
                    if debug_items and len(work_items) >= debug_items:
                        if logger:
                            logger.info(f"🔍 调试模式: 限制为 {debug_items} 个新项目")
                        break
                    
                    work_items.append(item)
                
                if not work_items:
                    if logger:
                        logger.info(f"✅ 文件已完成: {filename}")
                        logger.log_file_processing(filename, "already_complete", 0, 0)
                    return
                
                if logger:
                    logger.info(f"⚙️ 开始处理 {len(work_items)} 个项目")
                    # 创建文件级进度条
                    progress_bar = logger.create_progress_bar(
                        f"file_{filename}", 
                        len(work_items), 
                        f"处理 {filename}"
                    )
                
                # Process in batches
                n_success = 0
                batch_count = 0
                
                for i in range(0, len(work_items), self.chunk_size):
                    batch = work_items[i:i + self.chunk_size]
                    batch_count += 1
                    
                    # Process batch concurrently
                    batch_results = await self.concurrent_scorer.score_batch(
                        batch, self.input_key, self.prompt_format_key
                    )
                    
                    n_success_batch = 0
                    for result in batch_results:
                        status = result.get("api_status", "unknown")
                        if status == "success":
                            n_success_batch += 1
                            
                        # 记录到批量日志
                        if logger:
                            logger.log_batch_item({
                                "file": filename,
                                "item_id": result.get("id", "unknown"),
                                "status": status,
                                "score": result.get("score"),
                                "fail_reason": result.get("api_fail_reason", "")
                            })
                        
                        processed_items.append(result)
                    
                    n_success += n_success_batch
                    
                    # 更新进度条
                    if logger:
                        logger.update_progress(f"file_{filename}", len(batch))
                    
                    # Intermediate save (cumulative, only successful ones)
                    if (self.parquet_save_interval > 0 and 
                        len(processed_items) % self.parquet_save_interval == 0):
                        successful_items = [item for item in processed_items if item.get("api_status") == "success"]
                        if successful_items:
                            if logger:
                                logger.info(f"💾 中间保存: {len(successful_items)} 个成功结果 (累积模式)")
                            writer = DataWriter(self.output_fs)
                            # 累积式保存：保存所有成功的item，不是覆盖
                            writer.write(output_path, successful_items)
                    
                    # 每10个批次输出一次进度
                    if batch_count % 10 == 0 and logger:
                        success_rate = n_success / (batch_count * self.chunk_size) * 100
                        logger.info(f"进度: 批次 {batch_count}, 成功率 {success_rate:.1f}%")
                
                # 关闭进度条
                if logger:
                    logger.close_progress_bar(f"file_{filename}")
                    
                success_rate = n_success / len(work_items) * 100
                if logger:
                    logger.info(f"✅ 文件处理完成: {filename}")
                    logger.info(f"   总体成功率: {n_success}/{len(work_items)} ({success_rate:.1f}%)")
                
                # Write final results (only successful ones)
                successful_items = [item for item in processed_items if item.get("api_status") == "success"]
                if successful_items:
                    writer = DataWriter(self.output_fs)
                    writer.write(output_path, successful_items)
                    if logger:
                        logger.info(f"📁 写入 {len(successful_items)} 个成功项目到输出文件")
                elif processed_items:
                    if logger:
                        logger.warning(f"⚠️ 所有 {len(processed_items)} 个项目都失败了，不写入输出文件")
                
                # 记录文件处理结果
                if logger:
                    logger.log_file_processing(filename, "success", len(work_items), n_success)
                
                # Update status file if stat_folder is provided
                if self.stat_folder:
                    await self._update_stat_file(input_path, output_path, processed_items)
                
            except Exception as e:
                if logger:
                    logger.error(f"🚨 处理文件错误 {filename}: {e}")
                    logger.log_file_processing(filename, "error", 0, 0)
                raise
            
            finally:
                if logger:
                    logger.info(f"🔴 完成处理: {filename}")
    
    async def _update_stat_file(self, input_path: str, output_path: str, processed_items: List[Dict[str, Any]]) -> None:
        """Update status file with processing results."""
        if not self.stat_folder:
            return
        
        stat_path = os.path.join(self.stat_folder, os.path.basename(input_path) + ".json")
        
        # Load existing stat or create new one
        stat_data = load_progress_stat(stat_path) or copy.deepcopy(DEFAULT_FILE_STAT)
        
        # Update stat data
        stat_data["raw_file_path"] = input_path
        stat_data["formatted_file_path"] = output_path
        
        # Add to tagged file paths if not already present
        if output_path not in stat_data.get("taged_file_paths", []):
            stat_data.setdefault("taged_file_paths", []).append(output_path)
        
        # Count successful items
        successful_items = [item for item in processed_items if item.get("api_status") == "success"]
        stat_data["n_sucess_sample"] = len(successful_items)
        stat_data["n_sample"] = len(processed_items)
        
        # Save updated stat
        save_progress_stat(stat_path, stat_data)
    
    async def process_files(self,
                          files: List[str],
                          resume: bool = True,
                          debug_items: Optional[int] = None,
                          delete_existing: bool = False) -> None:
        """Process multiple files concurrently."""
        
        # Ensure output directory exists
        self.output_fs.makedirs(self.output_folder, exist_ok=True)
        
        # Handle existing files
        if delete_existing:
            existing_files = self.output_fs.glob(f"{self.output_folder}/*.parquet")
            for file_path in existing_files:
                print(f"[WARNING] Deleting existing file: {file_path}")
                self.output_fs.remove(file_path)
        
        # Copy config files to output folder for record
        await self._copy_config_files()
        
        # Create processing tasks
        tasks = []
        for input_path in files:
            # 强制输出为Parquet格式
            input_basename = os.path.basename(input_path)
            base_name = os.path.splitext(input_basename)[0]
            output_path = os.path.join(self.output_folder, f"{base_name}.parquet")
            task = self.process_single_file(
                input_path, output_path, resume, debug_items
            )
            tasks.append(task)
        
        print(f"Starting concurrent processing for {len(tasks)} files...")
        await asyncio.gather(*tasks)
        print("🎉 All files have been processed.")
    
    async def _copy_config_files(self) -> None:
        """Copy configuration files to output folder for record keeping."""
        try:
            import fsspec
            local_fs = fsspec.filesystem("file")
            
            for config_path in [self.api_scorer.model_config, self.api_scorer.prompt_config]:
                if hasattr(config_path, '__file__'):  # Skip if not a file path
                    continue
                    
                # This is a simplified version - in practice you'd want to track the actual config file paths
                # For now, we'll skip this step
                pass
                
        except Exception as e:
            print(f"Warning: Could not copy config files: {e}")

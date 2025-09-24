"""GitHub原始代码数据预处理脚本"""

import os
import json
import random
import argparse
import copy
from uuid import uuid4
from pathlib import Path
from typing import List, Dict, Any, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import pandas as pd
import numpy as np
import tiktoken

from ..utils import get_tos_config, get_filesystem, process_text
from .base import BasePreprocessor


DEFAULT_FILE_STAT = {
    "prompt_conf": "",
    "model_conf": "",
    "rating_times": 0,
    "voting_status": False,
    "raw_file_path": "",
    "formatted_file_path": "",
    "taged_file_paths": [],
    "voting_file_path": "",
    "n_sample": 0,
}


class GitHubRawCodePreprocessor(BasePreprocessor):
    """GitHub原始代码预处理器"""
    
    def __init__(self, raw_path: str, output_dir: str, stat_dir: str, 
                 fs_cfg: Dict[str, Any], max_tokens: int = 32768, 
                 num_proc: int = 32, seed: int = 42, num_files: int = -1):
        
        super().__init__(raw_path, output_dir, stat_dir, fs_cfg, max_tokens, num_proc)
        
        self.seed = seed
        self.num_files = num_files
        
        # 设置随机种子
        random.seed(seed)
        np.random.seed(seed)
        
        print(f"GitHubRawCodePreprocessor initialized:")
        print(f"  Raw path: {raw_path}")
        print(f"  Output dir: {output_dir}")
        print(f"  Stat dir: {stat_dir}")
        print(f"  Max tokens: {max_tokens}")
        print(f"  Num processes: {num_proc}")
    
    def get_file_list(self) -> List[Tuple[str, str, str]]:
        """获取要处理的文件列表，返回(input_file, output_file, stat_file)"""
        
        # 判断输入路径类型（本地 vs TOS）
        if self.raw_path.startswith(("tos://", "/")):
            # TOS路径或绝对路径
            search_path = self.raw_path
            if self.raw_path.startswith("tos://"):
                fs = get_filesystem(search_path, self.fs_cfg)
            else:
                from ..fs.local import LocalFileSystem
                fs = LocalFileSystem()
        else:
            # 相对路径，假设是TOS
            search_path = f"tos://agi-data/{self.raw_path}"
            fs = get_filesystem(search_path, self.fs_cfg)
        
        # 查找支持的文件格式
        file_patterns = ["*.parquet", "*.jsonl"]
        all_files = []
        
        for pattern in file_patterns:
            try:
                files = fs.glob(os.path.join(search_path, pattern))
                all_files.extend(files)
            except Exception as e:
                print(f"Warning: Could not search for {pattern}: {e}")
        
        print(f"Found {len(all_files)} files (parquet/jsonl) in {search_path}")
        
        # 构建输入输出文件列表
        all_input_files = []
        all_output_files = []
        
        for file_path in all_files:
            # 处理输入文件路径
            if self.raw_path.startswith("tos://"):
                # TOS输入
                if file_path.startswith("tos://"):
                    input_file = file_path
                else:
                    input_file = f"tos://{file_path}"
                
                # TOS输出，强制Parquet格式
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                output_file = os.path.join(f"tos://agi-data/{self.output_dir}", 
                                         f"{base_name}.parquet")
            else:
                # 本地文件
                input_file = file_path
                
                # 本地输出，强制Parquet格式
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                output_file = os.path.join(self.output_dir, f"{base_name}.parquet")
            
            all_input_files.append(input_file)
            all_output_files.append(output_file)
        
        # 限制处理文件数量
        if self.num_files > 0:
            all_input_files = all_input_files[:self.num_files]
            all_output_files = all_output_files[:self.num_files]
        
        print(f"Will process {len(all_input_files)} files")
        if all_input_files:
            print(f"Examples:")
            for i, (inp, out) in enumerate(zip(all_input_files[:3], all_output_files[:3])):
                print(f"  {i+1}. {os.path.basename(inp)} -> {os.path.basename(out)}")
        
        # 检查进度并确定需要处理的文件
        files_to_process = []
        n_completed = 0
        n_no_stat = 0
        
        for input_file, output_file in zip(all_input_files, all_output_files):
            # 解析相对路径
            rel_path = input_file.split(self.raw_path.rstrip('/'))[-1].lstrip("/")
            progress_stat_file = os.path.join(self.stat_dir, rel_path + ".json")
            
            # 确保stat目录存在
            os.makedirs(os.path.dirname(progress_stat_file), exist_ok=True)
            
            # 检查是否已经处理过
            if os.path.exists(progress_stat_file):
                try:
                    with open(progress_stat_file, "r", encoding="utf-8") as f:
                        stat = json.load(f)
                    if stat.get("formatted_file_path"):
                        n_completed += 1
                        continue  # 已经处理过，跳过
                except Exception:
                    n_no_stat += 1  # stat文件存在但读取失败
            else:
                n_no_stat += 1  # stat文件不存在
            
            files_to_process.append((input_file, output_file, progress_stat_file))
        
        print(f"Progress check: {n_completed} completed, {n_no_stat} to process")
        
        return files_to_process
    
    def process_single_file(self, input_path: str, output_path: str) -> Tuple[bool, int]:
        """处理单个文件，支持Parquet和JSONL输入"""
        try:
            # 根据文件扩展名读取文件
            file_ext = os.path.splitext(input_path)[1].lower()
            fs = get_filesystem(input_path, self.fs_cfg)
            
            if file_ext == '.parquet':
                with fs.open(input_path, "rb") as f:
                    df = pd.read_parquet(f)
            elif file_ext == '.jsonl':
                import json
                lines = []
                with fs.open(input_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                lines.append(json.loads(line))
                            except json.JSONDecodeError as e:
                                print(f"Warning: Skipping invalid JSON line: {e}")
                df = pd.DataFrame(lines)
            else:
                raise ValueError(f"Unsupported file format: {file_ext}. Supported: .parquet, .jsonl")
            
            print(f"Processing {os.path.basename(input_path)} ({file_ext}): {len(df)} rows")
            print(f"Columns: {list(df.columns)}")
            
            df_sampled = df.copy()
            
            # 创建截断的文本字段
            new_column_name = f'content_truncate_{self.max_tokens//1024}k'
            
            # 使用text字段进行截断
            if 'text' in df_sampled.columns:
                df_sampled[new_column_name] = df_sampled['text'].apply(
                    process_text, args=(self.enc, self.max_tokens)
                )
            else:
                print(f"Warning: 'text' column not found, available columns: {list(df_sampled.columns)}")
                # 尝试使用其他可能的文本字段
                text_candidates = ['content', 'code', 'body', 'description']
                text_field = None
                for candidate in text_candidates:
                    if candidate in df_sampled.columns:
                        text_field = candidate
                        break
                
                if text_field:
                    print(f"Using '{text_field}' as text field")
                    df_sampled['text'] = df_sampled[text_field]
                    df_sampled[new_column_name] = df_sampled['text'].apply(
                        process_text, args=(self.enc, self.max_tokens)
                    )
                else:
                    raise ValueError(f"No suitable text field found in columns: {list(df_sampled.columns)}")
            
            # 确保有ID字段
            if 'id' not in df_sampled.columns:
                print("ID field not found, generating new IDs")
                df_sampled['id'] = [str(uuid4()) for _ in range(len(df_sampled))]
            
            # 确保有source字段
            if 'source' not in df_sampled.columns:
                df_sampled['source'] = 'github_raw_code'
            
            n_sample = len(df_sampled)
            
            # 强制保存为Parquet格式
            output_fs = get_filesystem(output_path, self.fs_cfg)
            
            # 确保输出路径是.parquet结尾
            if not output_path.endswith('.parquet'):
                base_name = os.path.splitext(output_path)[0]
                output_path = f"{base_name}.parquet"
            
            with output_fs.open(output_path, "wb") as f:
                df_sampled.to_parquet(f, engine='pyarrow')
            
            print(f"Saved {n_sample} samples to {os.path.basename(output_path)} (Parquet format)")
            return True, n_sample
            
        except Exception as e:
            print(f"Failed to process file {input_path}: {e}")
            return False, 0
    
    def worker(self, args_tuple: Tuple[str, str, str]) -> Tuple[str, bool]:
        """工作进程函数"""
        input_file, output_file, progress_stat_file = args_tuple
        
        success, n_sample = self.process_single_file(input_file, output_file)
        
        # 更新统计文件
        stat = copy.deepcopy(DEFAULT_FILE_STAT)
        stat["raw_file_path"] = input_file
        stat["formatted_file_path"] = output_file if success else ""
        stat["n_sample"] = n_sample
        
        try:
            with open(progress_stat_file, "w", encoding="utf-8") as f:
                json.dump(stat, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to write stat file {progress_stat_file}: {e}")
        
        return (input_file, success)
    
    def run(self):
        """运行预处理"""
        print("=== GitHub Raw Code Preprocessing ===")
        
        # 保存配置
        os.makedirs(self.stat_dir, exist_ok=True)
        config_path = os.path.join(self.stat_dir, "preprocess_config.json")
        config_to_save = {
            "raw_path": self.raw_path,
            "output_dir": self.output_dir,
            "stat_dir": self.stat_dir,
            "max_tokens": self.max_tokens,
            "num_proc": self.num_proc,
            "seed": self.seed,
            "num_files": self.num_files
        }
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        
        # 获取要处理的文件
        files_to_process = self.get_file_list()
        
        if not files_to_process:
            print("No files to process!")
            return
        
        print(f"Processing {len(files_to_process)} files with {self.num_proc} processes")
        
        # 多进程处理
        n_success = 0
        n_fail = 0
        
        with ProcessPoolExecutor(max_workers=self.num_proc) as executor:
            futures = [executor.submit(self.worker, args_tuple) for args_tuple in files_to_process]
            
            with tqdm(total=len(futures), desc="Processing files") as pbar:
                for future in as_completed(futures):
                    input_file, success = future.result()
                    if success:
                        n_success += 1
                    else:
                        n_fail += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({"Success": n_success, "Fail": n_fail})
        
        print(f"=== Processing completed ===")
        print(f"Success: {n_success}, Failed: {n_fail}")
        success_rate = n_success / (n_success + n_fail) * 100 if (n_success + n_fail) > 0 else 0
        print(f"Success rate: {success_rate:.2f}%")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="Preprocess GitHub raw code dataset")
    
    parser.add_argument("--raw_path", type=str, required=True,
                       help="Directory of the raw code dataset")
    parser.add_argument("--output_dir", type=str, required=True,
                       help="Directory to save the processed dataset")
    parser.add_argument("--stat_dir", type=str, required=True,
                       help="Directory to save processing statistics")
    parser.add_argument("--num_proc", type=int, default=32,
                       help="Number of processes to use for preprocessing")
    parser.add_argument("--max_tokens", type=int, default=32768,
                       help="Maximum number of tokens per example")
    parser.add_argument("--num_files", type=int, default=-1,
                       help="Number of files to process (-1 for all)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed for sampling")
    
    args = parser.parse_args()
    
    # 获取TOS配置
    ak, sk, endpoint, region = get_tos_config()
    fs_cfg = {"tos": {"ak": ak, "sk": sk, "endpoint": endpoint, "region": region}}
    
    # 创建并运行预处理器
    preprocessor = GitHubRawCodePreprocessor(
        raw_path=args.raw_path,
        output_dir=args.output_dir,
        stat_dir=args.stat_dir,
        fs_cfg=fs_cfg,
        max_tokens=args.max_tokens,
        num_proc=args.num_proc,
        seed=args.seed,
        num_files=args.num_files
    )
    
    preprocessor.run()


if __name__ == "__main__":
    main()

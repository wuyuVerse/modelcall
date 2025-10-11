"""三元组过滤数据预处理器 - 处理issue2commit的pt_data_filtered数据"""

from __future__ import annotations

import os
import json
import copy
import glob
from uuid import uuid4
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict

import pandas as pd

from ..base import BasePreprocessor
from ...common.utils import get_filesystem, process_text


class TripletFilterPreprocessor(BasePreprocessor):
    """三元组过滤数据预处理器"""
    
    def __init__(self, 
                 raw_path: str,
                 output_dir: str,
                 stat_dir: str,
                 fs_cfg: Dict[str, Any],
                 max_tokens: int = 32768,
                 num_proc: int = 16,
                 batch_size: int = 1000,
                 group_by_language: bool = True):
        super().__init__(raw_path, output_dir, stat_dir, fs_cfg, max_tokens, num_proc, batch_size)
        self.group_by_language = group_by_language
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
    
    def get_file_list(self) -> List[Tuple[str, str]]:
        """获取文件列表 - 按语言分组处理"""
        # 获取所有jsonl文件
        pattern = os.path.join(self.raw_path, "pt_data_*.jsonl")
        input_files = glob.glob(pattern)
        
        if not input_files:
            print(f"No files found matching pattern: {pattern}")
            return []
        
        # 按语言分组
        language_files = defaultdict(list)
        for file_path in input_files:
            # 从文件名提取语言信息: pt_data_Python_part01.jsonl -> Python
            filename = os.path.basename(file_path)
            if filename.startswith("pt_data_") and filename.endswith(".jsonl"):
                # 移除前缀和后缀，提取语言和部分信息
                name_part = filename[8:-6]  # 移除 "pt_data_" 和 ".jsonl"
                # 找到最后一个 "_part" 来分离语言和部分
                if "_part" in name_part:
                    language = name_part.rsplit("_part", 1)[0]
                else:
                    language = name_part
                
                language_files[language].append(file_path)
        
        # 生成文件对列表
        file_pairs = []
        for language, files in language_files.items():
            # 对于每种语言，创建一个输出文件
            output_file = os.path.join(self.output_dir, f"{language}.parquet")
            
            # 将该语言的所有输入文件映射到同一个输出文件
            # 这里我们用第一个文件作为代表，实际处理时会合并所有文件
            file_pairs.append((language, output_file))
        
        print(f"Found {len(language_files)} languages with {sum(len(files) for files in language_files.values())} total files")
        for lang, files in language_files.items():
            print(f"  {lang}: {len(files)} files")
        
        return file_pairs
    
    def process_single_file(self, language: str, output_path: str) -> Tuple[bool, int]:
        """处理单个语言的所有文件，合并到一个输出文件"""
        try:
            # 获取该语言的所有输入文件
            pattern = os.path.join(self.raw_path, f"pt_data_{language}_*.jsonl")
            input_files = glob.glob(pattern)
            
            if not input_files:
                print(f"No files found for language: {language}")
                return False, 0
            
            print(f"Processing {len(input_files)} files for language: {language}")
            
            # 读取所有文件的数据
            all_data = []
            for input_file in sorted(input_files):
                print(f"  Reading: {os.path.basename(input_file)}")
                fs = get_filesystem(input_file, self.fs_cfg)
                
                # 读取JSONL文件
                with fs.open(input_file, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            all_data.append(item)
                        except json.JSONDecodeError as e:
                            print(f"    Warning: JSON decode error in {input_file} line {line_num}: {e}")
                            continue
            
            print(f"  Total items loaded: {len(all_data)}")
            
            # 处理数据
            fs = get_filesystem(output_path, self.fs_cfg)
            from ...common.data_io import DataWriter
            writer = DataWriter(fs)
            
            return self.process_data_with_batching(all_data, output_path, writer)
            
        except Exception as e:
            print(f"Failed to process language {language}: {e}")
            return False, 0
    
    def process_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理单个三元组数据项"""
        result = copy.deepcopy(item)
        
        # 添加ID如果缺失
        if 'id' not in result:
            result['id'] = str(uuid4())
        
        # 处理text字段 - 这是包含代码仓库XML内容的字段，直接作为评分内容
        if 'text' in result and result['text']:
            # 截断处理，生成用于评分的内容
            processed_text = process_text(result['text'], self.enc, self.max_tokens)
            result[f'content_truncate_{self.max_tokens//1024}k'] = processed_text
            
            # 为提示词模板提供一些基本的占位符值
            result.update({
                'repo_full_name': 'Code Repository',
                'language': result.get('lg', 'Unknown'),
                'files_with_content': 'Multiple',
                'total_lines': 'Large',
                'has_readme': 'Unknown',
                'has_license': 'Unknown', 
                'has_gitignore': 'Unknown'
            })
        
        return result
    
    
    def get_text_field(self, item: Dict[str, Any]) -> Optional[str]:
        """获取文本字段名称"""
        return 'text'
    
    def process_worker(self, args_tuple: Tuple[str, str, str]) -> Tuple[str, bool]:
        """重写worker函数以处理语言分组"""
        language, output_file, progress_stat_file = args_tuple
        
        # 记录开始时间
        from datetime import datetime
        start_time = datetime.now()
        
        success, n_sample = self.process_single_file(language, output_file)
        
        # 记录结束时间
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # 保存进度统计
        from ...common.utils import DEFAULT_FILE_STAT, save_progress_stat
        stat = copy.deepcopy(DEFAULT_FILE_STAT)
        stat["raw_file_path"] = f"Language: {language}"
        stat["formatted_file_path"] = output_file if success else ""
        stat["n_sample"] = n_sample
        stat["processing_complete"] = success
        stat["start_time"] = start_time.isoformat()
        stat["end_time"] = end_time.isoformat()
        stat["processing_time_seconds"] = processing_time
        stat["batch_size"] = self.batch_size
        stat["max_tokens"] = self.max_tokens
        stat["language"] = language
        
        save_progress_stat(progress_stat_file, stat)
        
        return language, success


def main():
    """命令行入口"""
    import argparse
    from ...common.utils import get_tos_config
    
    parser = argparse.ArgumentParser(description="Triplet filter data preprocessing")
    parser.add_argument("--raw_path", type=str, required=True,
                       help="Path to raw triplet data directory")
    parser.add_argument("--output_dir", type=str, required=True,
                       help="Output directory for processed data")
    parser.add_argument("--stat_dir", type=str, required=True,
                       help="Directory for progress statistics")
    parser.add_argument("--num_proc", type=int, default=16,
                       help="Number of processes")
    parser.add_argument("--max_tokens", type=int, default=32768,
                       help="Maximum tokens per sample")
    parser.add_argument("--batch_size", type=int, default=1000,
                       help="Batch size for processing")
    
    args = parser.parse_args()
    
    # 获取文件系统配置
    ak, sk, endpoint, region = get_tos_config()
    fs_cfg = {"tos": {"ak": ak, "sk": sk, "endpoint": endpoint, "region": region}}
    
    # 创建预处理器
    preprocessor = TripletFilterPreprocessor(
        raw_path=args.raw_path,
        output_dir=args.output_dir,
        stat_dir=args.stat_dir,
        fs_cfg=fs_cfg,
        max_tokens=args.max_tokens,
        num_proc=args.num_proc,
        batch_size=args.batch_size
    )
    
    # 运行预处理
    preprocessor.run()


if __name__ == "__main__":
    main()

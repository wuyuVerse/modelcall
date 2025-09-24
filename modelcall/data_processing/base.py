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

from ..utils import DEFAULT_FILE_STAT, save_progress_stat, load_progress_stat, get_filesystem, process_text
from ..data_io import DataReader, DataWriter


class BasePreprocessor:
    """Base class for data preprocessing."""
    
    def __init__(self, 
                 raw_path: str,
                 output_dir: str,
                 stat_dir: str,
                 fs_cfg: Dict[str, Any],
                 max_tokens: int = 32768,
                 num_proc: int = 32):
        self.raw_path = raw_path
        self.output_dir = output_dir
        self.stat_dir = stat_dir
        self.fs_cfg = fs_cfg
        self.max_tokens = max_tokens
        self.num_proc = num_proc
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
            
            # Process data
            processed_data = []
            for item in data:
                processed_item = self.process_item(item)
                if processed_item:
                    processed_data.append(processed_item)
            
            # Write processed data
            writer.write(output_path, processed_data)
            
            return True, len(processed_data)
            
        except Exception as e:
            print(f"Failed to process file {input_path}: {e}")
            return False, 0
    
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
        n_no_stat = 0
        
        for input_file, output_file in file_pairs:
            # Create progress stat file path
            rel_path = input_file.split(self.raw_path)[-1].lstrip("/")
            progress_stat_file = os.path.join(self.stat_dir, rel_path + ".json")
            
            # Check if already processed
            stat = load_progress_stat(progress_stat_file)
            if stat and stat.get("formatted_file_path"):
                n_completed += 1
                continue
            else:
                n_no_stat += 1
            
            files_to_process.append((input_file, output_file, progress_stat_file))
        
        print(f"Progress check: {n_completed} completed, {n_no_stat} to process")
        return files_to_process
    
    def process_worker(self, args_tuple: Tuple[str, str, str]) -> Tuple[str, bool]:
        """Worker function for multiprocessing."""
        input_file, output_file, progress_stat_file = args_tuple
        
        success, n_sample = self.process_single_file(input_file, output_file)
        
        # Save progress
        stat = copy.deepcopy(DEFAULT_FILE_STAT)
        stat["raw_file_path"] = input_file
        stat["formatted_file_path"] = output_file if success else ""
        stat["n_sample"] = n_sample
        
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


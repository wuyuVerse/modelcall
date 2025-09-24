"""GitHub code data preprocessing."""

from __future__ import annotations

import os
import json
import random
from typing import List, Tuple, Dict, Any

import numpy as np

from .base import BasePreprocessor, create_base_parser
from ..utils import get_tos_config


class GitHubPreprocessor(BasePreprocessor):
    """Preprocessor for GitHub code data."""
    
    def get_file_list(self) -> List[Tuple[str, str]]:
        """Get list of parquet files from TOS."""
        from ..fs.tos import TOSFileSystem
        from ..fs.base import FSConfig
        
        # Build TOS filesystem
        tos_config = self.fs_cfg.get("tos", {})
        config = FSConfig(
            bucket=tos_config.get("bucket", "agi-data"),
            endpoint=tos_config.get("endpoint"),
            root=tos_config.get("prefix")
        )
        tos_fs = TOSFileSystem(config)
        
        # Get file list
        base_path = f"tos://agi-data/{self.raw_path}"
        file_names = tos_fs.glob(os.path.join(base_path, "*.parquet"))
        
        all_input_files = []
        all_output_files = []
        
        for file_path in file_names:
            input_file = f"tos://{file_path}"
            output_file = os.path.join(f"tos://agi-data/{self.output_dir}", 
                                     os.path.basename(file_path))
            all_input_files.append(input_file)
            all_output_files.append(output_file)
        
        return list(zip(all_input_files, all_output_files))
    
    def get_text_field(self, item: Dict[str, Any]) -> str:
        """GitHub data uses 'text' field."""
        return "text"


def main():
    """Main entry point for GitHub preprocessing."""
    parser = create_base_parser()
    args = parser.parse_args()
    
    # Save config
    config_path = os.path.join(args.stat_dir, "preprocess_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(vars(args), f, indent=2, ensure_ascii=False)
    
    # Set random seeds
    random.seed(args.seed)
    np.random.seed(args.seed)
    
    # Get TOS configuration
    ak, sk, endpoint, region = get_tos_config()
    fs_cfg = {"tos": {"ak": ak, "sk": sk, "endpoint": endpoint, "region": region}}
    
    # Create and run preprocessor
    preprocessor = GitHubPreprocessor(
        raw_path=args.raw_path,
        output_dir=args.output_dir,
        stat_dir=args.stat_dir,
        fs_cfg=fs_cfg,
        max_tokens=args.max_tokens,
        num_proc=args.num_proc
    )
    
    preprocessor.run()


if __name__ == "__main__":
    main()


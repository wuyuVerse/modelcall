"""Utility functions for TOS configuration and filesystem operations."""

import os
from typing import Tuple, Dict, Any, Optional
import pandas as pd
import json
from pathlib import Path


def get_tos_config() -> Tuple[str, str, str, str]:
    """Get TOS configuration from environment variables."""
    ak = os.getenv("TOS_ACCESS_KEY", "")
    sk = os.getenv("TOS_SECRET_KEY", "")
    endpoint = os.getenv("TOS_ENDPOINT", "")
    region = os.getenv("REGION", "cn-beijing")
    return ak, sk, endpoint, region


def get_filesystem(path: str, fs_cfg: Dict[str, Any]):
    """Get filesystem instance based on path prefix and config."""
    from .fs.local import LocalFileSystem
    from .fs.tos import TOSFileSystem
    from .fs.base import FSConfig
    
    if path.startswith("tos://"):
        tos_config = fs_cfg.get("tos", {})
        config = FSConfig(
            bucket=tos_config.get("bucket"),
            endpoint=tos_config.get("endpoint"),
            root=tos_config.get("prefix")
        )
        return TOSFileSystem(config)
    else:
        return LocalFileSystem()


def is_tos_parquet_file_complete(path: str) -> bool:
    """Check if TOS parquet file is complete (placeholder)."""
    # TODO: Implement actual TOS file completeness check
    return True


def process_text(text: str, enc, max_tokens: int) -> str:
    """
    检查文本长度，如果超过 20K，则进行编码并截断。
    """
    if len(text) > 20000:
        tokens = enc.encode(text, disallowed_special=())
        truncated_tokens = tokens[:max_tokens]
        return enc.decode(truncated_tokens)
    else:
        return text


def save_progress_stat(stat_file: str, stat_data: Dict[str, Any]) -> None:
    """Save processing progress statistics to JSON file."""
    os.makedirs(os.path.dirname(stat_file), exist_ok=True)
    with open(stat_file, "w", encoding="utf-8") as f:
        json.dump(stat_data, f, indent=2, ensure_ascii=False)


def load_progress_stat(stat_file: str) -> Optional[Dict[str, Any]]:
    """Load processing progress statistics from JSON file."""
    if not os.path.exists(stat_file):
        return None
    try:
        with open(stat_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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

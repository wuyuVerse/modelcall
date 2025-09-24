"""Data I/O module supporting multiple formats (jsonl, parquet)."""

from __future__ import annotations

import json
import pandas as pd
from typing import Iterable, Dict, Any, Union, BinaryIO
from pathlib import Path

from .fs.base import FileSystem


class DataReader:
    """Unified data reader for multiple formats."""
    
    def __init__(self, fs: FileSystem):
        self.fs = fs
    
    def read(self, path: str, format: str = "auto") -> Iterable[Dict[str, Any]]:
        """Read data from path with specified format."""
        if format == "auto":
            format = self._detect_format(path)
        
        if format == "jsonl":
            return self._read_jsonl(path)
        elif format == "parquet":
            return self._read_parquet(path)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _detect_format(self, path: str) -> str:
        """Auto-detect format from file extension."""
        ext = Path(path).suffix.lower()
        if ext == ".jsonl":
            return "jsonl"
        elif ext == ".parquet":
            return "parquet"
        else:
            raise ValueError(f"Cannot detect format from extension: {ext}")
    
    def _read_jsonl(self, path: str) -> Iterable[Dict[str, Any]]:
        """Read JSONL format."""
        with self.fs.open(path, "rb") as f:
            for line in f:
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                yield json.loads(line)
    
    def _read_parquet(self, path: str) -> Iterable[Dict[str, Any]]:
        """Read Parquet format."""
        with self.fs.open(path, "rb") as f:
            df = pd.read_parquet(f)
            for _, row in df.iterrows():
                yield row.to_dict()


class DataWriter:
    """Unified data writer for multiple formats."""
    
    def __init__(self, fs: FileSystem):
        self.fs = fs
    
    def write(self, path: str, data: Iterable[Dict[str, Any]], format: str = "auto") -> None:
        """Write data to path with specified format."""
        if format == "auto":
            format = self._detect_format(path)
        
        if format == "jsonl":
            self._write_jsonl(path, data)
        elif format == "parquet":
            self._write_parquet(path, data)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _detect_format(self, path: str) -> str:
        """Auto-detect format from file extension."""
        ext = Path(path).suffix.lower()
        if ext == ".jsonl":
            return "jsonl"
        elif ext == ".parquet":
            return "parquet"
        else:
            raise ValueError(f"Cannot detect format from extension: {ext}")
    
    def _write_jsonl(self, path: str, data: Iterable[Dict[str, Any]]) -> None:
        """Write JSONL format."""
        with self.fs.open(path, "wb") as f:
            for obj in data:
                f.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    
    def _write_parquet(self, path: str, data: Iterable[Dict[str, Any]]) -> None:
        """Write Parquet format."""
        # Convert generator to list to create DataFrame
        df = pd.DataFrame(list(data))
        with self.fs.open(path, "wb") as f:
            df.to_parquet(f, engine='pyarrow', index=False)

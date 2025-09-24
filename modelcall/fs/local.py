from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, BinaryIO
import glob as py_glob

from .base import FileSystem, FSConfig


class LocalFileSystem(FileSystem):
	def __init__(self, config: FSConfig | None = None):
		self.root = Path(config.root) if config and config.root else Path.cwd()

	def _resolve(self, path: str) -> Path:
		p = Path(path)
		return p if p.is_absolute() else (self.root / p)

	def open(self, path: str, mode: str = "rb") -> BinaryIO:
		full = self._resolve(path)
		if any(flag in mode for flag in ("w", "a", "+")):
			full.parent.mkdir(parents=True, exist_ok=True)
		return open(full, mode)

	def exists(self, path: str) -> bool:
		return self._resolve(path).exists()

	def listdir(self, path: str) -> Iterable[str]:
		full = self._resolve(path)
		if not full.exists():
			return []
		return [str(p) for p in full.iterdir()]

	def makedirs(self, path: str, exist_ok: bool = True) -> None:
		self._resolve(path).mkdir(parents=True, exist_ok=exist_ok)

	def glob(self, pattern: str) -> Iterable[str]:
		"""Glob pattern matching for local paths."""
		# Resolve the pattern to an absolute path
		resolved_pattern = str(self._resolve(pattern))
		return py_glob.glob(resolved_pattern)

	def remove(self, path: str) -> None:
		full = self._resolve(path)
		if full.is_dir():
			for child in full.iterdir():
				if child.is_file():
					child.unlink(missing_ok=True)
				else:
					# shallow remove only for simplicity; extend as needed
					child.unlink(missing_ok=True)
			full.rmdir()
		else:
			full.unlink(missing_ok=True)

from __future__ import annotations

import os
import io
from typing import Iterable, BinaryIO
from urllib.parse import urlparse

from .base import FileSystem, FSConfig


class TOSFileSystem(FileSystem):
	"""TOS filesystem adapter using tosfs."""

	def __init__(self, config: FSConfig | None = None):
		self.bucket = (config.bucket if config else None) or os.getenv("TOS_BUCKET", "agi-data")
		self.endpoint = (config.endpoint if config else None) or os.getenv("TOS_ENDPOINT", "")
		self.root = (config.root if config else None) or os.getenv("TOS_PREFIX", "")
		
		# Initialize TOS client
		try:
			import tosfs
			ak = os.getenv("TOS_ACCESS_KEY", "")
			sk = os.getenv("TOS_SECRET_KEY", "")
			region = os.getenv("REGION", "cn-beijing")
			
			self.fs = tosfs.TosFileSystem(
				key=ak,
				secret=sk,
				endpoint=self.endpoint,
				region=region
			)
		except ImportError:
			raise ImportError("tosfs not installed. Install with: pip install tosfs")

	def _normalize_path(self, path: str) -> str:
		"""Convert tos:// URLs to bucket/key format."""
		if path.startswith("tos://"):
			parsed = urlparse(path)
			bucket = parsed.netloc or self.bucket
			key = parsed.path.lstrip("/")
			return f"{bucket}/{key}"
		return f"{self.bucket}/{path.lstrip('/')}"

	def open(self, path: str, mode: str = "rb") -> BinaryIO:
		normalized_path = self._normalize_path(path)
		return self.fs.open(normalized_path, mode)

	def exists(self, path: str) -> bool:
		normalized_path = self._normalize_path(path)
		return self.fs.exists(normalized_path)

	def listdir(self, path: str) -> Iterable[str]:
		normalized_path = self._normalize_path(path)
		try:
			return self.fs.ls(normalized_path, detail=False)
		except Exception:
			return []

	def glob(self, pattern: str) -> Iterable[str]:
		"""Glob pattern matching for TOS paths."""
		normalized_pattern = self._normalize_path(pattern)
		return self.fs.glob(normalized_pattern)

	def makedirs(self, path: str, exist_ok: bool = True) -> None:
		# No-op for object storage
		pass

	def remove(self, path: str) -> None:
		normalized_path = self._normalize_path(path)
		self.fs.rm(normalized_path)

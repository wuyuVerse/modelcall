from __future__ import annotations

from typing import Protocol, Iterable, Optional, BinaryIO


class FileSystem(Protocol):
	def open(self, path: str, mode: str = "rb") -> BinaryIO:  # read/write handled by mode
		...

	def exists(self, path: str) -> bool:
		...

	def listdir(self, path: str) -> Iterable[str]:
		...

	def makedirs(self, path: str, exist_ok: bool = True) -> None:
		...

	def remove(self, path: str) -> None:
		...


class FSConfig:
	"""Basic FS configuration carrier."""

	def __init__(self, root: Optional[str] = None, bucket: Optional[str] = None, endpoint: Optional[str] = None):
		self.root = root
		self.bucket = bucket
		self.endpoint = endpoint

from __future__ import annotations

import json
from typing import Iterable, Dict, Any

from ..fs.base import FileSystem
from .scorer import Scorer


def iter_jsonl(fs: FileSystem, path: str) -> Iterable[Dict[str, Any]]:
	with fs.open(path, "rb") as f:
		for line in f:
			line = line.decode("utf-8").strip()
			if not line:
				continue
			yield json.loads(line)


def write_jsonl(fs: FileSystem, path: str, records: Iterable[Dict[str, Any]]) -> None:
	with fs.open(path, "wb") as f:
		for obj in records:
			f.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))


def run_pipeline(fs: FileSystem, scorer: Scorer, input_path: str, output_path: str) -> None:
	results = (scorer.score(item) for item in iter_jsonl(fs, input_path))
	write_jsonl(fs, output_path, results)

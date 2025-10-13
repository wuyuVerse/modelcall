"""数据管道命令"""

from __future__ import annotations

from .common import build_fs


def cmd_pipeline(args) -> None:
	"""Run the scoring pipeline."""
	from ..data_scoring.scorer import DummyScorer
	from ..data_scoring.runner import run_pipeline
	
	fs = build_fs(args.fs, args.root)
	scorer = DummyScorer()
	run_pipeline(fs, scorer, args.input, args.output)


def register_pipeline_parser(subparsers):
	"""注册 pipeline 命令的参数解析器"""
	import os
	
	pipeline_parser = subparsers.add_parser("pipeline", help="Run scoring pipeline")
	pipeline_parser.add_argument("input", help="Input JSONL/Parquet path")
	pipeline_parser.add_argument("output", help="Output JSONL/Parquet path")
	pipeline_parser.add_argument("--fs", default="local", choices=["local", "tos"], help="Filesystem backend")
	pipeline_parser.add_argument("--root", default=os.getenv("DATA_ROOT", None), help="FS root/prefix for relative paths")
	pipeline_parser.set_defaults(func=cmd_pipeline)


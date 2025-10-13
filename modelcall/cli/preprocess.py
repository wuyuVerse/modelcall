"""预处理命令"""

from __future__ import annotations


def cmd_preprocess_github(args) -> None:
	"""Run GitHub raw code preprocessing."""
	# 设置环境变量（防止错误）
	import os
	os.environ.setdefault("BASE_URL", "")
	os.environ.setdefault("API_KEY", "")
	
	# 准备参数
	import sys
	original_argv = sys.argv.copy()
	sys.argv = [
		"github_preprocess",
		"--raw_path", args.raw_path,
		"--output_dir", args.output_dir, 
		"--stat_dir", args.stat_dir,
		"--num_proc", str(args.num_proc),
		"--max_tokens", str(args.max_tokens),
		"--num_files", str(args.num_files),
		"--seed", str(args.seed)
	]
	
	try:
		from ..data_processing.preprocessors.github_raw_code import main as github_preprocess_main
		github_preprocess_main()
	finally:
		# 恢复原始argv
		sys.argv = original_argv


def cmd_preprocess_repomix(args) -> None:
	"""Run Repomix XML preprocessing."""
	# 设置环境变量（防止错误）
	import os
	os.environ.setdefault("BASE_URL", "")
	os.environ.setdefault("API_KEY", "")
	
	# 准备参数
	import sys
	original_argv = sys.argv.copy()
	sys.argv = [
		"repomix_preprocess",
		"--raw_path", args.raw_path,
		"--output_dir", args.output_dir, 
		"--stat_dir", args.stat_dir,
		"--num_proc", str(args.num_proc),
		"--max_tokens", str(args.max_tokens),
		"--num_files", str(args.num_files),
		"--seed", str(args.seed)
	]
	
	# 添加languages参数
	if args.languages:
		sys.argv.extend(["--languages"] + args.languages)
	
	try:
		from ..data_processing.preprocessors.repo_xml import main as repomix_preprocess_main
		repomix_preprocess_main()
	finally:
		# 恢复原始argv
		sys.argv = original_argv


def register_preprocess_parsers(subparsers):
	"""注册预处理命令的参数解析器"""
	preprocess_parser = subparsers.add_parser("preprocess", help="Data preprocessing")
	preprocess_subparsers = preprocess_parser.add_subparsers(dest="preprocess_type", help="Preprocessing type")
	
	# GitHub preprocessing
	github_parser = preprocess_subparsers.add_parser("github", help="Preprocess GitHub code data")
	github_parser.add_argument("--raw_path", type=str, required=True, help="Path to raw GitHub data")
	github_parser.add_argument("--output_dir", type=str, required=True, help="Output directory")
	github_parser.add_argument("--stat_dir", type=str, required=True, help="Statistics directory")
	github_parser.add_argument("--num_proc", type=int, default=32, help="Number of processes")
	github_parser.add_argument("--max_tokens", type=int, default=32768, help="Maximum tokens")
	github_parser.add_argument("--num_files", type=int, default=-1, help="Number of files (-1 for all)")
	github_parser.add_argument("--seed", type=int, default=42, help="Random seed")
	github_parser.set_defaults(func=cmd_preprocess_github)
	
	# Repomix XML preprocessing
	repomix_parser = preprocess_subparsers.add_parser("repomix", help="Preprocess Repomix XML files")
	repomix_parser.add_argument("--raw_path", type=str, required=True, help="Path to repomix_output directory")
	repomix_parser.add_argument("--output_dir", type=str, required=True, help="Output directory")
	repomix_parser.add_argument("--stat_dir", type=str, required=True, help="Statistics directory")
	repomix_parser.add_argument("--num_proc", type=int, default=16, help="Number of processes")
	repomix_parser.add_argument("--max_tokens", type=int, default=32768, help="Maximum tokens")
	repomix_parser.add_argument("--num_files", type=int, default=-1, help="Number of files (-1 for all)")
	repomix_parser.add_argument("--seed", type=int, default=42, help="Random seed")
	repomix_parser.add_argument("--languages", type=str, nargs="+", default=None, help="Languages to process")
	repomix_parser.set_defaults(func=cmd_preprocess_repomix)


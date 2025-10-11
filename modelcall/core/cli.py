from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from ..fs.base import FSConfig
from ..fs.local import LocalFileSystem
try:
	from ..fs.tos import TOSFileSystem
except Exception:  # pragma: no cover
	TOSFileSystem = None  # type: ignore

from ..data_scoring.scorer import DummyScorer
from ..data_scoring.runner import run_pipeline


def build_fs(backend: str, root: str | None) -> object:
	cfg = FSConfig(root=root)
	if backend == "local":
		return LocalFileSystem(cfg)
	elif backend == "tos":
		if TOSFileSystem is None:
			raise RuntimeError("TOS backend unavailable. Install SDK and implement.")
		return TOSFileSystem(cfg)  # type: ignore
	else:
		raise ValueError(f"Unknown fs backend: {backend}")


def cmd_pipeline(args) -> None:
	"""Run the scoring pipeline."""
	fs = build_fs(args.fs, args.root)
	scorer = DummyScorer()
	run_pipeline(fs, scorer, args.input, args.output)


def cmd_preprocess_github(args) -> None:
	"""Run GitHub data preprocessing."""
	from ..data_processing.github_preprocess import GitHubPreprocessor
	from ..common.utils import get_tos_config
	
	# Get TOS configuration
	ak, sk, endpoint, region = get_tos_config()
	fs_cfg = {"tos": {"ak": ak, "sk": sk, "endpoint": endpoint, "region": region}}
	
	preprocessor = GitHubPreprocessor(
		raw_path=args.raw_path,
		output_dir=args.output_dir,
		stat_dir=args.stat_dir,
		fs_cfg=fs_cfg,
		max_tokens=args.max_tokens,
		num_proc=args.num_proc
	)
	preprocessor.run()


def cmd_api_call(args) -> None:
	"""Run concurrent API calling with two-level concurrency."""
	import asyncio
	from ..data_scoring.concurrent_processor import ConcurrentFileProcessor
	from ..common.utils import get_tos_config
	
	# Get TOS configuration
	ak, sk, endpoint, region = get_tos_config()
	fs_cfg = {"tos": {"ak": ak, "sk": sk, "endpoint": endpoint, "region": region}}
	
	# Create processor
	processor = ConcurrentFileProcessor(
		input_folder=args.input_folder,
		output_folder=args.output_folder,
		stat_folder=args.stat_folder,
		model_config_path=args.model_config_path,
		prompt_config_path=args.prompt_config_path,
		fs_cfg=fs_cfg,
		max_concurrent_files=args.max_concurrent_files,
		max_concurrent_requests=args.max_concurrent_requests,
		chunk_size=args.chunk_size,
		parquet_save_interval=args.parquet_save_interval,
		input_key=args.input_key,
		prompt_format_key=args.prompt_format_key,
		enable_format_validation_retry=not args.disable_format_validation_retry
	)
	
	# Get files to process with distributed processing support
	files = processor.get_files_to_process(
		debug_files=args.debug_files,
		job_index=args.job_index, 
		world_size=args.world_size
	)
	
	if not files:
		print(f"No parquet files found in {args.input_folder} for job {args.job_index}/{args.world_size}")
		return
	
	print(f"Job {args.job_index}/{args.world_size}: Found {len(files)} files to process")
	
	# Run async processing
	asyncio.run(processor.process_files(
		files=files,
		resume=not args.no_resume,
		debug_items=args.debug_items,
		delete_existing=args.delete_existing
	))


def cmd_run_task(args) -> None:
	"""Run task using task configuration file."""
	import asyncio
	import yaml
	from pathlib import Path
	from .task_manager import TaskManager
	from .logging import setup_logging, cleanup_logging
	from ..data_distillation.batch_submit_runner import BatchSubmitRunner
	
	# 加载配置文件
	config_path = Path(args.task_config)
	with open(config_path, 'r', encoding='utf-8') as f:
		config = yaml.safe_load(f)
	
	task_type = config.get('task_type')
	task_name = config.get('task_name', 'unknown_task')
	
	# 设置日志
	logging_config = config.get('logging', {})
	log_level = logging_config.get('level', 'INFO')
	log_dir = logging_config.get('log_dir', 'logs')
	
	setup_logging(
		task_name=task_name,
		job_index=0,
		world_size=1,
		log_dir=log_dir,
		log_level=log_level
	)
	
	try:
		# 如果是批量提交任务，使用专门的执行器
		if task_type == "batch_distillation_submit":
			runner = BatchSubmitRunner(config)
			runner.run()
			return
		
		# 如果是合并结果任务，使用专门的执行器
		if task_type == "merge_distillation_results":
			from ..data_distillation.merge_results_runner import MergeResultsRunner
			runner = MergeResultsRunner(config)
			runner.run()
			return
	finally:
		cleanup_logging()
	
	# 其他任务类型使用 TaskManager
	task_manager = TaskManager(args.task_config)
	
	# Print configuration summary
	task_manager.print_config_summary()
	
	# Run the task
	asyncio.run(task_manager.run_task(
		job_index=args.job_index,
		world_size=args.world_size
	))


def cmd_distillation_generate(args) -> None:
	"""Run response generation task."""
	import asyncio
	import json
	import yaml
	from pathlib import Path
	from ..data_distillation import ResponseGenerator
	from .logging import setup_logging, cleanup_logging, get_logger
	
	# 生成任务名称
	input_file_name = Path(args.input_path).stem
	task_name = f"response_gen_{input_file_name}"
	
	# 设置日志
	setup_logging(
		task_name=task_name,
		job_index=0,
		world_size=1,
		log_dir=args.log_dir,
		log_level=args.log_level
	)
	
	logger = get_logger()
	
	try:
		# 加载模型配置
		logger.info(f"加载模型配置: {args.model_config}")
		config_path = Path(args.model_config)
		
		if not config_path.exists():
			raise FileNotFoundError(f"模型配置文件不存在: {config_path}")
		
		with open(config_path, 'r', encoding='utf-8') as f:
			if config_path.suffix in ['.yaml', '.yml']:
				model_config = yaml.safe_load(f)
			elif config_path.suffix == '.json':
				model_config = json.load(f)
			else:
				raise ValueError(f"不支持的配置文件格式: {config_path.suffix}")
		
		if "client_config" not in model_config or "chat_config" not in model_config:
			raise ValueError("模型配置文件必须包含 client_config 和 chat_config")
		
		client_config = model_config["client_config"]
		chat_config = model_config["chat_config"]
		
		logger.info(f"模型: {chat_config.get('model', 'unknown')}")
		logger.info(f"输入文件: {args.input_path}")
		logger.info(f"输出目录: {args.output_path}")
		logger.info(f"并发数: {args.concurrency}")
		logger.info(f"批量大小: {args.batch_size}")
		logger.info(f"重试模式: {args.retry}")
		logger.info(f"断点续传: {not args.no_resume}")
		
		# 创建响应生成器
		generator = ResponseGenerator(
			input_path=args.input_path,
			output_path=args.output_path,
			client_config=client_config,
			chat_config=chat_config,
			concurrency=args.concurrency,
			batch_size=args.batch_size,
			flush_interval_secs=args.flush_interval,
			retry_mode=args.retry,
			resume_mode=not args.no_resume
		)
		
		# 运行生成
		asyncio.run(generator.run())
		
		logger.info("响应生成任务完成!")
		
	except Exception as e:
		logger.error(f"任务执行失败: {e}", exc_info=True)
		raise
	
	finally:
		cleanup_logging()




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


def main() -> None:
	load_dotenv()

	parser = argparse.ArgumentParser(description="ModelCall data processing pipeline")
	subparsers = parser.add_subparsers(dest="command", help="Available commands")
	
	# Pipeline command
	pipeline_parser = subparsers.add_parser("pipeline", help="Run scoring pipeline")
	pipeline_parser.add_argument("input", help="Input JSONL/Parquet path")
	pipeline_parser.add_argument("output", help="Output JSONL/Parquet path")
	pipeline_parser.add_argument("--fs", default="local", choices=["local", "tos"], help="Filesystem backend")
	pipeline_parser.add_argument("--root", default=os.getenv("DATA_ROOT", None), help="FS root/prefix for relative paths")
	pipeline_parser.set_defaults(func=cmd_pipeline)
	
	# Preprocessing commands
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
	
	# API calling command
	api_parser = subparsers.add_parser("api-call", help="Concurrent API calling for scoring")
	api_parser.add_argument("--input_folder", type=str, required=True, help="Input folder with parquet files")
	api_parser.add_argument("--output_folder", type=str, required=True, help="Output folder for scored files")
	api_parser.add_argument("--stat_folder", type=str, default=None, help="Statistics folder for progress tracking")
	api_parser.add_argument("--model_config_path", type=str, required=True, help="Path to model config YAML")
	api_parser.add_argument("--prompt_config_path", type=str, required=True, help="Path to prompt config YAML")
	api_parser.add_argument("--max_concurrent_files", type=int, default=2, help="Max concurrent files")
	api_parser.add_argument("--max_concurrent_requests", type=int, default=10, help="Max concurrent API requests")
	api_parser.add_argument("--chunk_size", type=int, default=100, help="Batch size for processing")
	api_parser.add_argument("--parquet_save_interval", type=int, default=-1, help="Interval for intermediate saves")
	api_parser.add_argument("--input_key", type=str, default="text", help="Input text field name")
	api_parser.add_argument("--prompt_format_key", type=str, default="code_corpus_description_and_sample", help="Prompt template key")
	api_parser.add_argument("--debug_files", type=int, default=None, help="Limit number of files for debugging")
	api_parser.add_argument("--debug_items", type=int, default=None, help="Limit number of items per file for debugging")
	api_parser.add_argument("--no_resume", action="store_true", help="Don't resume from existing output")
	api_parser.add_argument("--delete_existing", action="store_true", help="Delete existing output files")
	api_parser.add_argument("--disable_format_validation_retry", action="store_true", help="Disable retry when JSON format validation fails")
	api_parser.add_argument("--job_index", type=int, default=0, help="Job index for distributed processing")
	api_parser.add_argument("--world_size", type=int, default=1, help="Total number of jobs for distributed processing")
	api_parser.set_defaults(func=cmd_api_call)
	
	# Task runner command
	task_parser = subparsers.add_parser("run-task", help="Run task using configuration file")
	task_parser.add_argument("task_config", help="Path to task configuration YAML file")
	task_parser.add_argument("--job_index", type=int, default=0, help="Job index for distributed processing")
	task_parser.add_argument("--world_size", type=int, default=None, help="Override world size from config")
	task_parser.set_defaults(func=cmd_run_task)
	
	# Distillation generate command (single response generation task)
	distillation_parser = subparsers.add_parser("distillation-generate", help="Run single response generation task")
	distillation_parser.add_argument("--input-path", "-i", required=True, help="输入 JSONL 文件路径")
	distillation_parser.add_argument("--output-path", "-o", required=True, help="输出目录路径")
	distillation_parser.add_argument("--model-config", "-m", required=True, help="模型配置文件路径")
	distillation_parser.add_argument("--concurrency", "-c", type=int, default=30, help="并发数")
	distillation_parser.add_argument("--batch-size", "-b", type=int, default=30, help="批量保存大小")
	distillation_parser.add_argument("--flush-interval", "-f", type=float, default=2.0, help="刷新间隔（秒）")
	distillation_parser.add_argument("--retry", action="store_true", help="重试模式")
	distillation_parser.add_argument("--no-resume", action="store_true", help="禁用断点续传")
	distillation_parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
	distillation_parser.add_argument("--log-dir", default="/volume/pt-train/users/wzhang/wjj-workspace/modelcall/logs", help="日志目录")
	distillation_parser.set_defaults(func=cmd_distillation_generate)
	
	args = parser.parse_args()
	
	if hasattr(args, 'func'):
		args.func(args)
	else:
		parser.print_help()


if __name__ == "__main__":
	main()

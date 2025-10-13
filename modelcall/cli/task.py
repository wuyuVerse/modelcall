"""任务执行命令（run-task）"""

from __future__ import annotations

import asyncio
import yaml
from pathlib import Path

from .common import run_response_generation


def cmd_run_task(args) -> None:
	"""Run task using task configuration file.
	
	统一入口：所有通过 YAML 配置文件驱动的任务都从这里执行
	支持的任务类型：
	  - batch_distillation_submit: SiFlow批量任务提交
	  - generate_response: 单文件响应生成
	  - merge_distillation_results: 合并蒸馏结果
	  - 其他: 数据评分等任务（通过 TaskManager）
	"""
	from ..core.task_manager import TaskManager
	from ..core.logging import setup_logging, cleanup_logging, get_logger
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
		# === 数据蒸馏相关任务 ===
		
		# 批量提交任务（提交到 SiFlow）
		if task_type == "batch_distillation_submit":
			runner = BatchSubmitRunner(config)
			runner.run()
			return
		
		# 单文件响应生成任务
		if task_type == "generate_response":
			logger = get_logger()
			dist_cfg = config.get("distillation", {})
			
			run_response_generation(
				input_path=dist_cfg.get("input_path"),
				output_path=dist_cfg.get("output_path"),
				model_config_path=dist_cfg.get("model_config"),
				concurrency=int(dist_cfg.get("concurrency", 30)),
				batch_size=int(dist_cfg.get("batch_size", 30)),
				flush_interval=float(dist_cfg.get("flush_interval", 2.0)),
				retry_mode=bool(dist_cfg.get("retry_mode", False)),
				resume_mode=bool(dist_cfg.get("resume", True)),
				logger=logger
			)
			return
		
		# 合并结果任务
		if task_type == "merge_distillation_results":
			from ..data_distillation.merge_results_runner import MergeResultsRunner
			runner = MergeResultsRunner(config)
			runner.run()
			return
		
		# === 其他任务类型（数据评分等）===
		# 注意：这部分会在 finally 之后执行 cleanup_logging，
		# 但 TaskManager.run_task 内部也有自己的日志管理
		
	finally:
		cleanup_logging()
	
	# 其他任务类型使用 TaskManager
	task_manager = TaskManager(args.task_config)
	task_manager.print_config_summary()
	
	asyncio.run(task_manager.run_task(
		job_index=args.job_index,
		world_size=args.world_size
	))


def register_task_parser(subparsers):
	"""注册 run-task 命令的参数解析器"""
	task_parser = subparsers.add_parser("run-task", help="Run task using configuration file")
	task_parser.add_argument("task_config", help="Path to task configuration YAML file")
	task_parser.add_argument("--job_index", type=int, default=0, help="Job index for distributed processing")
	task_parser.add_argument("--world_size", type=int, default=None, help="Override world size from config")
	task_parser.set_defaults(func=cmd_run_task)


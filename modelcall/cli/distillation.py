"""数据蒸馏命令（distillation-generate）"""

from __future__ import annotations

from pathlib import Path

from .common import run_response_generation


def cmd_distillation_generate(args) -> None:
	"""Run response generation task (CLI命令行方式).
	
	这个命令主要用于 SiFlow 提交的子任务，通过命令行参数传递配置。
	本地手动执行建议使用 'run-task' + YAML 配置文件的方式。
	"""
	from ..core.logging import setup_logging, cleanup_logging, get_logger
	
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
		run_response_generation(
			input_path=args.input_path,
			output_path=args.output_path,
			model_config_path=args.model_config,
			concurrency=args.concurrency,
			batch_size=args.batch_size,
			flush_interval=args.flush_interval,
			retry_mode=args.retry,
			resume_mode=not args.no_resume,
			logger=logger
		)
	except Exception as e:
		logger.error(f"任务执行失败: {e}", exc_info=True)
		raise
	finally:
		cleanup_logging()


def register_distillation_parser(subparsers):
	"""注册 distillation-generate 命令的参数解析器"""
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


"""API 调用命令"""

from __future__ import annotations


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


def register_api_call_parser(subparsers):
	"""注册 API 调用命令的参数解析器"""
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


"""ModelCall CLI - 命令行接口

重构后的 CLI 架构：
- common.py: 共享工具函数
- pipeline.py: 数据管道命令
- preprocess.py: 预处理命令
- api_call.py: API 调用命令
- task.py: 任务执行命令（run-task）
- distillation.py: 蒸馏命令（distillation-generate）
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from .pipeline import register_pipeline_parser
from .preprocess import register_preprocess_parsers
from .api_call import register_api_call_parser
from .task import register_task_parser
from .distillation import register_distillation_parser


def main() -> None:
	"""CLI 主入口"""
	load_dotenv()

	parser = argparse.ArgumentParser(description="ModelCall data processing pipeline")
	subparsers = parser.add_subparsers(dest="command", help="Available commands")
	
	# 注册所有命令的参数解析器
	register_pipeline_parser(subparsers)
	register_preprocess_parsers(subparsers)
	register_api_call_parser(subparsers)
	register_task_parser(subparsers)
	register_distillation_parser(subparsers)
	
	# 解析参数并执行命令
	args = parser.parse_args()
	
	if hasattr(args, 'func'):
		args.func(args)
	else:
		parser.print_help()


if __name__ == "__main__":
	main()


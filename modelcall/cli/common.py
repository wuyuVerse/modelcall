"""CLI 共享工具函数"""

from __future__ import annotations

import asyncio
import json
import yaml
from pathlib import Path


def build_fs(backend: str, root: str | None) -> object:
	"""构建文件系统"""
	from ..fs.base import FSConfig
	from ..fs.local import LocalFileSystem
	try:
		from ..fs.tos import TOSFileSystem
	except Exception:  # pragma: no cover
		TOSFileSystem = None  # type: ignore
	
	cfg = FSConfig(root=root)
	if backend == "local":
		return LocalFileSystem(cfg)
	elif backend == "tos":
		if TOSFileSystem is None:
			raise RuntimeError("TOS backend unavailable. Install SDK and implement.")
		return TOSFileSystem(cfg)  # type: ignore
	else:
		raise ValueError(f"Unknown fs backend: {backend}")


def run_response_generation(
	input_path: str,
	output_path: str,
	model_config_path: str,
	concurrency: int = 30,
	batch_size: int = 30,
	flush_interval: float = 2.0,
	retry_mode: bool = False,
	resume_mode: bool = True,
	logger = None
) -> None:
	"""共享的响应生成执行逻辑
	
	Args:
		input_path: 输入JSONL文件路径
		output_path: 输出目录路径
		model_config_path: 模型配置文件路径
		concurrency: 并发数
		batch_size: 批量保存大小
		flush_interval: 刷新间隔（秒）
		retry_mode: 是否为重试模式
		resume_mode: 是否启用断点续传
		logger: 日志记录器（可选）
	"""
	from ..data_distillation import ResponseGenerator
	
	if logger:
		logger.info(f"加载模型配置: {model_config_path}")
	
	cfg_path = Path(model_config_path)
	if not cfg_path.exists():
		raise FileNotFoundError(f"模型配置文件不存在: {cfg_path}")
	
	# 读取模型配置（支持 yaml/json）
	if cfg_path.suffix in [".yaml", ".yml"]:
		with open(cfg_path, 'r', encoding='utf-8') as f:
			model_cfg = yaml.safe_load(f)
	elif cfg_path.suffix == ".json":
		with open(cfg_path, 'r', encoding='utf-8') as f:
			model_cfg = json.load(f)
	else:
		raise ValueError(f"不支持的配置文件格式: {cfg_path.suffix}")
	
	if "client_config" not in model_cfg or "chat_config" not in model_cfg:
		raise ValueError("模型配置文件必须包含 client_config 和 chat_config")
	
	client_config = model_cfg["client_config"]
	chat_config = model_cfg["chat_config"]
	
	if logger:
		logger.info(f"模型: {chat_config.get('model', 'unknown')}")
		logger.info(f"输入文件: {input_path}")
		logger.info(f"输出目录: {output_path}")
		logger.info(f"并发数: {concurrency}")
		logger.info(f"批量大小: {batch_size}")
		logger.info(f"重试模式: {retry_mode}")
		logger.info(f"断点续传: {resume_mode}")
	
	generator = ResponseGenerator(
		input_path=input_path,
		output_path=output_path,
		client_config=client_config,
		chat_config=chat_config,
		concurrency=concurrency,
		batch_size=batch_size,
		flush_interval_secs=flush_interval,
		retry_mode=retry_mode,
		resume_mode=resume_mode
	)
	
	asyncio.run(generator.run())
	if logger:
		logger.info("响应生成任务完成!")


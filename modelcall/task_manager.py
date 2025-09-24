"""任务管理器 - 统一任务配置和执行"""

from __future__ import annotations

import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
from easydict import EasyDict

from .pipeline.concurrent_processor import ConcurrentFileProcessor
from .utils import get_tos_config
from .logging_manager import setup_logging, cleanup_logging, get_logger
from .data_processing.universal_preprocessor import create_preprocessor_from_config
from .data_processing.github_raw_code_preprocess import GitHubRawCodePreprocessor
from .data_processing.repo_xml_preprocess import RepoXMLPreprocessor


class TaskManager:
    """任务管理器"""
    
    def __init__(self, task_config_path: str):
        self.task_config_path = task_config_path
        self.config = self._load_task_config()
        self.fs_cfg = self._get_filesystem_config()
    
    def _load_task_config(self) -> EasyDict:
        """加载任务配置"""
        with open(self.task_config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return EasyDict(config)
    
    def _get_filesystem_config(self) -> Dict[str, Any]:
        """获取文件系统配置"""
        ak, sk, endpoint, region = get_tos_config()
        return {"tos": {"ak": ak, "sk": sk, "endpoint": endpoint, "region": region}}
    
    def _resolve_paths(self) -> Dict[str, str]:
        """解析配置中的路径，支持变量替换"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 路径变量替换
        replacements = {
            "{timestamp}": timestamp,
            "{task_name}": self.config.task_name
        }
        
        paths = {}
        
        # 处理输入输出路径
        input_folder = self.config.data.input_folder
        output_folder = self.config.data.output_folder
        stat_folder = self.config.data.stat_folder
        
        for key, value in replacements.items():
            output_folder = output_folder.replace(key, value)
            stat_folder = stat_folder.replace(key, value)
        
        # 添加TOS前缀（如果需要）- 只对相对路径（不以tos://、/、.开头）
        if not input_folder.startswith(("tos://", "/", "./")):
            input_folder = f"tos://agi-data/{input_folder}"
        if not output_folder.startswith(("tos://", "/", "./")):
            output_folder = f"tos://agi-data/{output_folder}"
        
        paths = {
            "input_folder": input_folder,
            "output_folder": output_folder,
            "stat_folder": stat_folder,
            "model_config_path": self.config.model.config_path,
            "prompt_config_path": self.config.prompt.config_path
        }
        
        return paths
    
    def _setup_environment(self) -> None:
        """设置环境变量"""
        env_config = self.config.get("environment", {})
        
        # 获取API环境配置文件路径
        api_env_file = env_config.get("config_path")
        
        if not api_env_file:
            print("⚠️ 未指定API环境配置文件")
            return
        
        # 加载API环境文件
        if os.path.exists(api_env_file):
            print(f"🔧 加载API环境配置: {api_env_file}")
            self._load_env_file(api_env_file)
            
            print(f"✅ API环境变量已加载: BASE_URL={os.environ.get('BASE_URL', 'Not set')}")
            print(f"✅ API环境变量已加载: API_KEY={os.environ.get('API_KEY', 'Not set')}")
        else:
            print(f"❌ API环境配置文件不存在: {api_env_file}")
        
        # 获取TOS环境配置文件路径（可选）
        tos_env_file = env_config.get("tos_config_path")
        if tos_env_file and os.path.exists(tos_env_file):
            print(f"🔧 加载TOS环境配置: {tos_env_file}")
            self._load_env_file(tos_env_file)
            print(f"✅ TOS环境变量已加载: TOS_ENDPOINT={os.environ.get('TOS_ENDPOINT', 'Not set')}")
        
        # 设置超时
        if "timeout" in env_config:
            os.environ["REQUEST_TIMEOUT"] = str(env_config["timeout"])
    
    def _load_env_file(self, env_file: str) -> None:
        """加载环境配置文件"""
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    # 处理 export VAR=value 格式
                    if line.startswith('export '):
                        line = line[7:]  # 移除 'export '
                    
                    # 分割变量名和值
                    key, value = line.split('=', 1)
                    # 移除引号
                    value = value.strip('"\'')
                    os.environ[key] = value
    
    def create_processor(self, job_index: int = 0, world_size: int = 1, run_index: int = 1) -> ConcurrentFileProcessor:
        """创建处理器实例"""
        paths = self._resolve_paths()
        
        # 如果是多轮运行，调整输出路径
        if self.config.distributed.get("num_runs", 1) > 1:
            output_folder = paths["output_folder"].replace("{run_index}", str(run_index))
            paths["output_folder"] = output_folder
        
        # 创建处理器
        processor = ConcurrentFileProcessor(
            input_folder=paths["input_folder"],
            output_folder=paths["output_folder"],
            stat_folder=paths["stat_folder"],
            model_config_path=paths["model_config_path"],
            prompt_config_path=paths["prompt_config_path"],
            fs_cfg=self.fs_cfg,
            max_concurrent_files=self.config.concurrency.max_concurrent_files,
            max_concurrent_requests=self.config.concurrency.max_concurrent_requests,
            chunk_size=self.config.concurrency.chunk_size,
            parquet_save_interval=self.config.concurrency.parquet_save_interval,
            input_key=self.config.data.input_key,
            prompt_format_key=self.config.data.prompt_format_key,
            enable_format_validation_retry=self.config.retry.enable_format_validation_retry
        )
        
        return processor
    
    async def run_preprocess(self, job_index: int = 0, world_size: int = None) -> None:
        """运行预处理任务"""
        if world_size is None:
            world_size = self.config.distributed.get("world_size", 1)
        
        preprocess_config = self.config.get("preprocess")
        if not preprocess_config:
            return
        
        logger = get_logger()
        if logger:
            logger.info("🔧 开始数据预处理...")
        
        # 解析预处理路径
        paths = self._resolve_paths()
        preprocess_input = preprocess_config.get("input_folder", paths["input_folder"])
        preprocess_output = preprocess_config.get("output_folder", paths["input_folder"] + "_preprocessed")
        
        # 检查是否使用自定义脚本
        script_type = preprocess_config.get("script_type", "universal")
        
        if script_type == "github_raw_code":
            # 使用GitHub原始代码预处理脚本
            if logger:
                logger.info("🔧 使用GitHub原始代码预处理脚本")
            
            # 处理调试模式的文件限制
            debug_max_files = None
            if self.config.debug.enabled and hasattr(self.config.debug, 'max_files'):
                debug_max_files = self.config.debug.max_files
            
            num_files = debug_max_files if debug_max_files is not None else preprocess_config.get("num_files", -1)
            
            preprocessor = GitHubRawCodePreprocessor(
                raw_path=preprocess_input,
                output_dir=preprocess_output.replace("tos://agi-data/", ""),  # 移除前缀
                stat_dir=paths["stat_folder"] + "_preprocess",
                fs_cfg=self.fs_cfg,
                max_tokens=preprocess_config.get("max_tokens", 32768),
                num_proc=preprocess_config.get("num_proc", 32),
                seed=preprocess_config.get("seed", 42),
                num_files=num_files
            )
            
            # 运行预处理
            preprocessor.run()
            
        elif script_type == "repo_xml":
            # 使用代码仓库XML/CXML预处理脚本
            if logger:
                logger.info("🔧 使用代码仓库XML/CXML预处理脚本")
            
            # 处理调试模式的文件限制
            debug_max_files = None
            if self.config.debug.enabled and hasattr(self.config.debug, 'max_files'):
                debug_max_files = self.config.debug.max_files
            
            num_files = debug_max_files if debug_max_files is not None else preprocess_config.get("num_files", -1)
            
            preprocessor = RepoXMLPreprocessor(
                raw_path=preprocess_input,
                output_dir=preprocess_output.replace("tos://agi-data/", ""),  # 移除前缀
                stat_dir=paths["stat_folder"] + "_preprocess",
                fs_cfg=self.fs_cfg,
                max_tokens=preprocess_config.get("max_tokens", 32768),
                num_proc=preprocess_config.get("num_proc", 16),
                seed=preprocess_config.get("seed", 42),
                num_files=num_files,
                languages=preprocess_config.get("languages")
            )
            
            # 运行预处理
            preprocessor.run()
            
        else:
            # 使用通用预处理器
            if logger:
                logger.info("🔧 使用通用预处理器")
            
            # 添加TOS前缀
            if not preprocess_input.startswith(("tos://", "/", ".")):
                preprocess_input = f"tos://agi-data/{preprocess_input}"
            if not preprocess_output.startswith(("tos://", "/", ".")):
                preprocess_output = f"tos://agi-data/{preprocess_output}"
            
            # 创建预处理器
            preprocessor = create_preprocessor_from_config(
                preprocess_config=preprocess_config,
                raw_path=preprocess_input,
                output_dir=preprocess_output,
                stat_dir=paths["stat_folder"] + "_preprocess",
                fs_cfg=self.fs_cfg,
                max_tokens=preprocess_config.get("max_tokens", 32768),
                num_proc=preprocess_config.get("num_proc", 32)
            )
            
            # 运行预处理
            preprocessor.run()
        
        if logger:
            logger.info("✅ 数据预处理完成")
        
        # 更新任务配置中的输入路径为预处理后的路径
        # 保持预处理输出路径的原始格式（本地/TOS）
        self.config.data.input_folder = preprocess_output

    async def run_task(self, job_index: int = 0, world_size: int = None) -> None:
        """运行任务（包括可选的预处理）"""
        # 使用配置中的world_size，除非明确指定
        if world_size is None:
            world_size = self.config.distributed.get("world_size", 1)
        
        # 设置日志系统
        logging_config = self.config.get("logging", {})
        logger = setup_logging(
            task_name=self.config.task_name,
            job_index=job_index,
            world_size=world_size,
            log_level=logging_config.get("level", "INFO")
        )
        
        # 设置批量日志大小
        if hasattr(logger, 'batch_size'):
            logger.batch_size = logging_config.get("batch_size", 100)
        
        try:
            self._setup_environment()
            
            logger.info(f"📋 任务描述: {self.config.description}")
            
            # 检查是否启用分布式
            if self.config.distributed.get("enabled", False) and world_size > 1:
                logger.info(f"🔀 分布式模式已启用")
            
            # 运行预处理（如果配置了）
            if self.config.get("preprocess") and self.config.preprocess.get("enabled", False):
                await self.run_preprocess(job_index, world_size)
            
            # 多轮运行支持
            num_runs = self.config.distributed.get("num_runs", 1)
            
            for run_index in range(1, num_runs + 1):
                if num_runs > 1:
                    logger.info(f"🎯 === 第 {run_index}/{num_runs} 轮运行 ===")
                
                # 创建处理器
                processor = self.create_processor(job_index, world_size, run_index)
                
                # 获取要处理的文件
                debug_files = self.config.debug.max_files if self.config.debug.enabled else None
                files = processor.get_files_to_process(
                    debug_files=debug_files,
                    job_index=job_index,
                    world_size=world_size
                )
                
                if not files:
                    logger.warning(f"没有找到要处理的文件 (Job {job_index}/{world_size})")
                    continue
                
                # 更新统计信息
                logger.update_stats(total_files=len(files))
                logger.info(f"📁 找到 {len(files)} 个文件需要处理")
                
                # 运行处理
                debug_items = self.config.debug.max_items_per_file if self.config.debug.enabled else None
                await processor.process_files(
                    files=files,
                    resume=self.config.options.resume,
                    debug_items=debug_items,
                    delete_existing=self.config.options.delete_existing
                )
                
                logger.info(f"✅ 第 {run_index} 轮运行完成")
            
            logger.info(f"🎉 任务 {self.config.task_name} 执行完成!")
            
        finally:
            # 清理日志系统
            cleanup_logging()
    
    def print_config_summary(self) -> None:
        """打印配置摘要"""
        print(f"\n📋 任务配置摘要:")
        print(f"   任务名称: {self.config.task_name}")
        print(f"   任务描述: {self.config.description}")
        
        paths = self._resolve_paths()
        print(f"   输入路径: {paths['input_folder']}")
        print(f"   输出路径: {paths['output_folder']}")
        print(f"   统计路径: {paths['stat_folder']}")
        
        print(f"   并发文件: {self.config.concurrency.max_concurrent_files}")
        print(f"   并发请求: {self.config.concurrency.max_concurrent_requests}")
        
        if self.config.distributed.enabled:
            print(f"   分布式: 启用 (World Size: {self.config.distributed.world_size})")
            if self.config.distributed.get("num_runs", 1) > 1:
                print(f"   多轮运行: {self.config.distributed.num_runs} 轮")
        else:
            print(f"   分布式: 禁用")
        
        if self.config.debug.enabled:
            print(f"   调试模式: 启用 (文件: {self.config.debug.max_files}, 项目: {self.config.debug.max_items_per_file})")


def load_task_manager(task_config_path: str) -> TaskManager:
    """加载任务管理器"""
    return TaskManager(task_config_path)

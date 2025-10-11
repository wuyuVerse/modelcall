"""任务管理器 - 统一任务配置和执行"""

from __future__ import annotations

import os
import asyncio
import glob
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import yaml
from easydict import EasyDict

from ..common.utils import get_tos_config
from .logging import setup_logging, cleanup_logging, get_logger
from .task_runners import PreprocessRunner, ScoringTaskRunner, DistillationTaskRunner


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
    
    def _find_latest_output_directory(self, base_output_path: str) -> Optional[str]:
        """查找最新的输出目录（用于跨时间戳断点续传）"""
        try:
            # 移除{timestamp}占位符，获取基础路径
            base_path = base_output_path.replace("/{timestamp}", "")
            
            # 如果是本地路径
            if base_path.startswith("./") or base_path.startswith("/"):
                if not os.path.exists(base_path):
                    return None
                
                # 查找所有时间戳目录
                timestamp_pattern = r"\d{8}_\d{6}"  # YYYYMMDD_HHMMSS
                dirs = []
                
                for item in os.listdir(base_path):
                    full_path = os.path.join(base_path, item)
                    if os.path.isdir(full_path) and re.match(timestamp_pattern, item):
                        dirs.append((item, full_path))
                
                if not dirs:
                    return None
                
                # 按时间戳排序，返回最新的
                dirs.sort(key=lambda x: x[0], reverse=True)
                latest_dir = dirs[0][1]
                
                # 检查目录中是否有parquet文件
                if glob.glob(os.path.join(latest_dir, "*.parquet")):
                    return latest_dir
                    
            # TODO: 添加对TOS路径的支持
            return None
            
        except Exception as e:
            logger = get_logger()
            if logger:
                logger.warning(f"查找最新输出目录时出错: {e}")
            return None
    
    def _resolve_paths(self) -> Dict[str, str]:
        """解析配置中的路径，支持变量替换和智能断点续传"""
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
        
        # 检查是否启用主处理断点续传
        main_resume = self.config.options.get('main_resume', self.config.options.get('resume', True))
        
        if main_resume and "{timestamp}" in output_folder:
            # 尝试查找最新的输出目录
            latest_dir = self._find_latest_output_directory(output_folder)
            if latest_dir:
                logger = get_logger()
                if logger:
                    logger.info(f"🔄 启用跨目录断点续传，使用现有目录: {latest_dir}")
                output_folder = latest_dir
                # 相应地更新stat_folder
                if "{timestamp}" in stat_folder:
                    # 从latest_dir提取时间戳
                    dir_name = os.path.basename(latest_dir)
                    stat_folder = stat_folder.replace("{timestamp}", dir_name)
            else:
                # 没有找到现有目录，使用新时间戳
                for key, value in replacements.items():
                    output_folder = output_folder.replace(key, value)
                    stat_folder = stat_folder.replace(key, value)
        else:
            # 不启用断点续传或没有时间戳占位符，正常替换
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
    
    def create_processor(self, job_index: int = 0, world_size: int = 1, run_index: int = 1):
        """创建处理器实例（向后兼容）"""
        paths = self._resolve_paths()
        logger = get_logger()
        
        # 创建评分任务执行器并获取处理器
        scoring_runner = ScoringTaskRunner(
            config=self.config,
            logger=logger,
            fs_cfg=self.fs_cfg,
            paths=paths
        )
        
        return scoring_runner.create_processor(job_index, world_size, run_index)
    
    async def run_preprocess(self, job_index: int = 0, world_size: int = None) -> None:
        """运行预处理任务"""
        if world_size is None:
            world_size = self.config.distributed.get("world_size", 1)
        
        paths = self._resolve_paths()
        logger = get_logger()
        
        # 创建预处理执行器并运行
        preprocess_runner = PreprocessRunner(
            config=self.config,
            logger=logger,
            fs_cfg=self.fs_cfg,
            paths=paths
        )
        
        preprocess_output = await preprocess_runner.run(job_index, world_size)
        
        # 更新配置（如果有输出）
        if preprocess_output:
            self.config.data.input_folder = preprocess_output

    async def run_distillation_task(self, job_index: int = 0, world_size: int = None) -> None:
        """运行数据蒸馏任务"""
        logger = get_logger()
        
        # 创建数据蒸馏执行器并运行
        distillation_runner = DistillationTaskRunner(
            config=self.config,
            logger=logger,
            fs_cfg=self.fs_cfg
        )
        
        await distillation_runner.run(job_index, world_size)

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
            
            task_type = self.config.get('task_type', 'unknown')
            logger.info(f"📋 任务类型: {task_type}")
            logger.info(f"📋 任务描述: {self.config.description}")
            
            # 根据任务类型分发到不同的处理逻辑
            if task_type == "data_distillation":
                # 数据蒸馏任务
                await self.run_distillation_task(job_index, world_size)
                logger.info(f"🎉 任务 {self.config.task_name} 执行完成!")
                return
            
            # 数据评分任务的处理逻辑
            # 运行预处理（如果配置了）
            if self.config.get("preprocess") and self.config.preprocess.get("enabled", False):
                await self.run_preprocess(job_index, world_size)
            
            # 创建评分任务执行器并运行
            paths = self._resolve_paths()
            scoring_runner = ScoringTaskRunner(
                config=self.config,
                logger=logger,
                fs_cfg=self.fs_cfg,
                paths=paths
            )
            
            await scoring_runner.run(job_index, world_size)
            
            logger.info(f"🎉 任务 {self.config.task_name} 执行完成!")
            
        finally:
            # 清理日志系统
            cleanup_logging()
    
    def print_config_summary(self) -> None:
        """打印配置摘要"""
        print(f"\n📋 任务配置摘要:")
        print(f"   任务名称: {self.config.task_name}")
        
        task_type = self.config.get('task_type', 'unknown')
        print(f"   任务类型: {task_type}")
        print(f"   任务描述: {self.config.description}")
        
        # 数据蒸馏任务的配置摘要
        if task_type == "data_distillation":
            distillation_config = self.config.get("distillation", {})
            print(f"   蒸馏步骤: {distillation_config.get('step', 'unknown')}")
            print(f"   输入目录: {distillation_config.get('input_dir', 'N/A')}")
            print(f"   输出目录: {distillation_config.get('output_dir', 'N/A')}")
            print(f"   并行进程数: {distillation_config.get('num_processes', 'N/A')}")
            print(f"   断点续传: {'启用' if distillation_config.get('continue_mode', True) else '禁用'}")
            return
        
        # 数据评分任务的配置摘要
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

"""基础任务执行器"""

from pathlib import Path
from typing import Dict, Any


class BaseTaskRunner:
    """任务执行器基类"""
    
    def __init__(self, config: Any, logger: Any, fs_cfg: Dict[str, Any]):
        """
        初始化任务执行器
        
        Args:
            config: 任务配置（EasyDict）
            logger: 日志管理器
            fs_cfg: 文件系统配置
        """
        self.config = config
        self.logger = logger
        self.fs_cfg = fs_cfg
    
    async def run(self, job_index: int = 0, world_size: int = 1):
        """
        运行任务（子类实现）
        
        Args:
            job_index: 作业索引
            world_size: 作业总数
        """
        raise NotImplementedError("Subclass must implement run() method")
    
    def _resolve_path(self, path: str, replacements: Dict[str, str]) -> str:
        """
        解析路径，支持变量替换
        
        Args:
            path: 原始路径
            replacements: 替换字典
            
        Returns:
            解析后的路径
        """
        for key, value in replacements.items():
            path = path.replace(key, value)
        return path


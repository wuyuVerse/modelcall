"""
ModelCall - 统一的数据处理平台

支持数据评分和数据蒸馏任务。

主要模块：
- core: 核心功能（CLI、任务管理、日志）
- common: 通用工具
- data_scoring: 数据评分
- data_processing: 数据预处理
- data_distillation: 数据蒸馏
- fs: 文件系统抽象
"""

__version__ = "1.0.0"

# 保持向后兼容的导入
from .core.cli import main
from .core.task_manager import TaskManager
from .core.logging import setup_logging, cleanup_logging, get_logger

__all__ = [
    "main",
    "TaskManager",
    "setup_logging",
    "cleanup_logging",
    "get_logger",
]


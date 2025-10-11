"""
ModelCall 核心模块

提供项目的核心功能，包括：
- CLI 命令行接口
- 任务管理和调度
- 日志管理系统
- 任务执行器
"""

from .cli import main
from .task_manager import TaskManager
from .logging import setup_logging, cleanup_logging, get_logger

__all__ = [
    "main",
    "TaskManager",
    "setup_logging",
    "cleanup_logging",
    "get_logger",
]


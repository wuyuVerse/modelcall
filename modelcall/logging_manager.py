"""统一日志管理系统"""

import os
import sys
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import contextmanager

import json
from tqdm import tqdm


@dataclass
class ProcessingStats:
    """处理统计信息"""
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    total_items: int = 0
    processed_items: int = 0
    success_items: int = 0
    failed_items: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    @property
    def success_rate(self) -> float:
        if self.processed_items == 0:
            return 0.0
        return self.success_items / self.processed_items * 100
    
    @property
    def processing_speed(self) -> float:
        """每分钟处理的项目数"""
        if self.elapsed_time == 0:
            return 0.0
        return self.processed_items / (self.elapsed_time / 60)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "success_items": self.success_items,
            "failed_items": self.failed_items,
            "elapsed_time": self.elapsed_time,
            "success_rate": self.success_rate,
            "processing_speed": self.processing_speed
        }


class ModelCallLogger:
    """ModelCall统一日志管理器"""
    
    def __init__(self, 
                 task_name: str,
                 job_index: int = 0,
                 world_size: int = 1,
                 log_dir: str = "./logs",
                 log_level: str = "INFO"):
        
        self.task_name = task_name
        self.job_index = job_index
        self.world_size = world_size
        self.log_dir = Path(log_dir)
        self.log_level = getattr(logging, log_level.upper())
        
        # 创建日志目录
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志文件路径
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if world_size > 1:
            log_filename = f"{task_name}_{timestamp}_job{job_index:03d}.log"
        else:
            log_filename = f"{task_name}_{timestamp}.log"
        
        self.log_file = self.log_dir / log_filename
        
        # 设置统计信息
        self.stats = ProcessingStats()
        
        # 进度条
        self.progress_bars: Dict[str, tqdm] = {}
        
        # 批量日志缓存
        self.batch_logs: List[Dict[str, Any]] = []
        self.batch_size = 100  # 每100条记录批量输出一次
        
        # 初始化日志器
        self._setup_logger()
        
        # 记录启动信息
        self.info(f"🚀 任务启动: {task_name}")
        if world_size > 1:
            self.info(f"🌐 分布式配置: Job {job_index}/{world_size}")
    
    def _setup_logger(self):
        """设置日志器"""
        # 创建日志器
        self.logger = logging.getLogger(f"modelcall.{self.task_name}.{self.job_index}")
        self.logger.setLevel(self.log_level)
        
        # 清除已有的handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # 文件处理器
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(self.log_level)
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        
        # 设置格式
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | Job%(job_index)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        file_handler.setFormatter(file_formatter)
        console_handler.setFormatter(console_formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # 添加job_index到日志记录中
        class JobIndexFilter(logging.Filter):
            def __init__(self, job_index):
                self.job_index = job_index
            
            def filter(self, record):
                record.job_index = self.job_index
                return True
        
        job_filter = JobIndexFilter(self.job_index)
        file_handler.addFilter(job_filter)
    
    def debug(self, message: str):
        """调试日志"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """信息日志"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """警告日志"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """错误日志"""
        self.logger.error(message)
    
    def critical(self, message: str):
        """严重错误日志"""
        self.logger.critical(message)
    
    def create_progress_bar(self, name: str, total: int, desc: str = None) -> tqdm:
        """创建进度条"""
        if desc is None:
            desc = name
        
        progress_bar = tqdm(
            total=total,
            desc=desc,
            unit="items",
            unit_scale=True,
            dynamic_ncols=True,
            position=len(self.progress_bars),
            leave=True
        )
        
        self.progress_bars[name] = progress_bar
        return progress_bar
    
    def update_progress(self, name: str, n: int = 1):
        """更新进度条"""
        if name in self.progress_bars:
            self.progress_bars[name].update(n)
    
    def close_progress_bar(self, name: str):
        """关闭进度条"""
        if name in self.progress_bars:
            self.progress_bars[name].close()
            del self.progress_bars[name]
    
    def log_batch_item(self, item_data: Dict[str, Any]):
        """添加项目到批量日志缓存"""
        self.batch_logs.append({
            "timestamp": datetime.now().isoformat(),
            "job_index": self.job_index,
            **item_data
        })
        
        # 如果达到批量大小，输出日志
        if len(self.batch_logs) >= self.batch_size:
            self.flush_batch_logs()
    
    def flush_batch_logs(self):
        """输出批量日志"""
        if not self.batch_logs:
            return
        
        # 统计批量信息
        batch_stats = {
            "batch_size": len(self.batch_logs),
            "success_count": len([log for log in self.batch_logs if log.get("status") == "success"]),
            "error_count": len([log for log in self.batch_logs if log.get("status") == "error"]),
        }
        
        # 输出批量统计信息
        success_rate = batch_stats["success_count"] / batch_stats["batch_size"] * 100
        self.info(f"📊 批量处理完成: {batch_stats['batch_size']} 项, "
                 f"成功 {batch_stats['success_count']}, "
                 f"失败 {batch_stats['error_count']}, "
                 f"成功率 {success_rate:.1f}%")
        
        # 保存详细日志到文件
        batch_log_file = self.log_dir / f"{self.task_name}_batch_details.jsonl"
        with open(batch_log_file, 'a', encoding='utf-8') as f:
            for log_entry in self.batch_logs:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        
        # 清空缓存
        self.batch_logs.clear()
    
    def update_stats(self, **kwargs):
        """更新统计信息"""
        for key, value in kwargs.items():
            if hasattr(self.stats, key):
                setattr(self.stats, key, value)
    
    def increment_stats(self, **kwargs):
        """增量更新统计信息"""
        for key, value in kwargs.items():
            if hasattr(self.stats, key):
                current_value = getattr(self.stats, key)
                setattr(self.stats, key, current_value + value)
    
    def log_file_processing(self, filename: str, status: str, 
                           items_processed: int = 0, items_success: int = 0):
        """记录文件处理结果"""
        self.info(f"📁 文件处理完成: {filename}")
        self.info(f"   状态: {status}")
        if items_processed > 0:
            success_rate = items_success / items_processed * 100
            self.info(f"   处理项目: {items_processed}, 成功: {items_success} ({success_rate:.1f}%)")
        
        # 更新统计
        self.increment_stats(processed_files=1)
        if status == "success":
            self.increment_stats(
                processed_items=items_processed,
                success_items=items_success,
                failed_items=items_processed - items_success
            )
        else:
            self.increment_stats(failed_files=1)
    
    def log_periodic_stats(self):
        """定期输出统计信息"""
        stats = self.stats.to_dict()
        
        self.info("=" * 60)
        self.info("📊 当前处理统计:")
        self.info(f"   文件进度: {stats['processed_files']}/{stats['total_files']}")
        self.info(f"   项目进度: {stats['processed_items']}/{stats['total_items']}")
        self.info(f"   成功率: {stats['success_rate']:.1f}%")
        self.info(f"   处理速度: {stats['processing_speed']:.1f} 项/分钟")
        self.info(f"   运行时间: {stats['elapsed_time']:.1f} 秒")
        self.info("=" * 60)
    
    @contextmanager
    def file_processing_context(self, filename: str):
        """文件处理上下文管理器"""
        start_time = time.time()
        self.info(f"📂 开始处理文件: {filename}")
        
        try:
            yield
            self.info(f"✅ 文件处理成功: {filename} (用时: {time.time() - start_time:.1f}s)")
        except Exception as e:
            self.error(f"❌ 文件处理失败: {filename} - {str(e)}")
            raise
    
    def save_final_stats(self):
        """保存最终统计信息"""
        stats_file = self.log_dir / f"{self.task_name}_final_stats.json"
        
        final_stats = {
            "task_name": self.task_name,
            "job_index": self.job_index,
            "world_size": self.world_size,
            "completion_time": datetime.now().isoformat(),
            "stats": self.stats.to_dict()
        }
        
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(final_stats, f, indent=2, ensure_ascii=False)
        
        self.info(f"📊 最终统计已保存: {stats_file}")
    
    def finalize(self):
        """完成日志记录"""
        # 输出剩余的批量日志
        self.flush_batch_logs()
        
        # 关闭所有进度条
        for name in list(self.progress_bars.keys()):
            self.close_progress_bar(name)
        
        # 输出最终统计
        self.log_periodic_stats()
        
        # 保存最终统计
        self.save_final_stats()
        
        self.info(f"🎉 任务完成: {self.task_name}")
        self.info(f"📄 日志文件: {self.log_file}")


# 全局日志管理器实例
_global_logger: Optional[ModelCallLogger] = None


def get_logger() -> Optional[ModelCallLogger]:
    """获取全局日志管理器"""
    return _global_logger


def setup_logging(task_name: str, job_index: int = 0, world_size: int = 1, 
                 log_dir: str = "./logs", log_level: str = "INFO") -> ModelCallLogger:
    """设置全局日志管理器"""
    global _global_logger
    _global_logger = ModelCallLogger(
        task_name=task_name,
        job_index=job_index,
        world_size=world_size,
        log_dir=log_dir,
        log_level=log_level
    )
    return _global_logger


def cleanup_logging():
    """清理日志管理器"""
    global _global_logger
    if _global_logger:
        _global_logger.finalize()
        _global_logger = None

"""数据评分任务执行器"""

from typing import Dict, Any

from .base_runner import BaseTaskRunner
from ...data_scoring.concurrent_processor import ConcurrentFileProcessor


class ScoringTaskRunner(BaseTaskRunner):
    """数据评分任务执行器"""
    
    def __init__(self, config: Any, logger: Any, fs_cfg: Dict[str, Any], paths: Dict[str, str]):
        """
        初始化数据评分执行器
        
        Args:
            config: 任务配置（EasyDict）
            logger: 日志管理器
            fs_cfg: 文件系统配置
            paths: 解析后的路径字典
        """
        super().__init__(config, logger, fs_cfg)
        self.paths = paths
    
    def create_processor(self, job_index: int = 0, world_size: int = 1, run_index: int = 1) -> ConcurrentFileProcessor:
        """
        创建处理器实例
        
        Args:
            job_index: 作业索引
            world_size: 作业总数
            run_index: 运行轮次
            
        Returns:
            ConcurrentFileProcessor 实例
        """
        paths = self.paths.copy()
        
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
    
    async def run(self, job_index: int = 0, world_size: int = 1):
        """
        运行数据评分任务
        
        Args:
            job_index: 作业索引
            world_size: 作业总数
        """
        # 检查是否启用分布式
        if self.config.distributed.get("enabled", False) and world_size > 1:
            self.logger.info(f"🔀 分布式模式已启用")
        
        # 多轮运行支持
        num_runs = self.config.distributed.get("num_runs", 1)
        
        for run_index in range(1, num_runs + 1):
            if num_runs > 1:
                self.logger.info(f"🎯 === 第 {run_index}/{num_runs} 轮运行 ===")
            
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
                self.logger.warning(f"没有找到要处理的文件 (Job {job_index}/{world_size})")
                continue
            
            # 更新统计信息
            self.logger.update_stats(total_files=len(files))
            self.logger.info(f"📁 找到 {len(files)} 个文件需要处理")
            
            # 运行处理
            debug_items = self.config.debug.max_items_per_file if self.config.debug.enabled else None
            await processor.process_files(
                files=files,
                resume=self.config.options.get('main_resume', self.config.options.get('resume', True)),
                debug_items=debug_items,
                delete_existing=self.config.options.delete_existing
            )
            
            self.logger.info(f"✅ 第 {run_index} 轮运行完成")


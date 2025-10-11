"""合并蒸馏结果执行器"""

from pathlib import Path
from typing import Dict, Any

from ..core.logging import get_logger
from .jsonl_utils import merge_split_results


class MergeResultsRunner:
    """合并蒸馏结果执行器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化合并结果执行器
        
        Args:
            config: 任务配置字典
        """
        self.config = config
        self.logger = get_logger()
        
        # 解析配置
        self.merge_config = config.get("merge", {})
    
    def merge_model_results(self, model_name: str) -> dict:
        """
        合并某个模型的结果
        
        Args:
            model_name: 模型名称
            
        Returns:
            合并统计信息
        """
        output_base_dir = self.merge_config.get("output_base_dir")
        merge_errors = self.merge_config.get("merge_errors", True)
        
        # 构建输入输出路径
        input_dir = Path(output_base_dir) / model_name
        output_file = Path(output_base_dir) / f"{model_name}_merged.jsonl"
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"合并模型: {model_name}")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"输入目录: {input_dir}")
        self.logger.info(f"输出文件: {output_file}")
        
        if not input_dir.exists():
            self.logger.warning(f"⚠️  目录不存在，跳过: {input_dir}")
            return {}
        
        # 执行合并
        try:
            stats = merge_split_results(
                input_dir=str(input_dir),
                output_file=str(output_file),
                merge_errors=merge_errors
            )
            
            self.logger.info(f"✅ {model_name} 合并完成")
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ {model_name} 合并失败: {e}", exc_info=True)
            return {}
    
    def run(self):
        """运行合并任务"""
        self.logger.info("=" * 60)
        self.logger.info(f"开始执行合并任务: {self.config.get('task_name', 'unknown')}")
        self.logger.info("=" * 60)
        
        models = self.merge_config.get("models", [])
        
        if not models:
            self.logger.error("未配置要合并的模型列表 (merge.models)")
            return
        
        self.logger.info(f"共需合并 {len(models)} 个模型的结果")
        
        # 合并每个模型的结果
        all_stats = {}
        
        for model in models:
            model_name = model.get("name")
            if not model_name:
                self.logger.warning("跳过未配置 name 的模型")
                continue
            
            stats = self.merge_model_results(model_name)
            all_stats[model_name] = stats
        
        # 打印总体统计
        self.logger.info("\n" + "=" * 60)
        self.logger.info("所有模型合并完成")
        self.logger.info("=" * 60)
        
        for model_name, stats in all_stats.items():
            if stats:
                self.logger.info(f"\n{model_name}:")
                self.logger.info(f"  成功记录: {stats.get('success_count', 0)}")
                self.logger.info(f"  错误记录: {stats.get('error_count', 0)}")
                self.logger.info(f"  成功率: {stats.get('success_rate', 0):.2f}%")
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info("任务完成")
        self.logger.info("=" * 60)


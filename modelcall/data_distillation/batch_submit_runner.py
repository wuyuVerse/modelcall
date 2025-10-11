"""批量提交任务执行器"""

from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

from ..siflow import BatchSubmitter
from ..core.logging import get_logger
from .jsonl_utils import split_jsonl, merge_split_results


class BatchSubmitRunner:
    """批量提交任务执行器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化批量提交执行器
        
        Args:
            config: 任务配置字典
        """
        self.config = config
        
        # 解析配置
        self.data_split_config = config.get("data_split", {})
        self.batch_submit_config = config.get("batch_submit", {})
        self.execution_config = config.get("execution", {})
        self.environment_config = config.get("environment", {})
        
        # 加载环境变量（在设置日志之前）
        self._load_environment()
        
        # 初始化日志（在加载环境变量之后）
        self.logger = get_logger()
    
    def _load_environment(self):
        """加载环境变量"""
        env_file = self.environment_config.get("env_file")
        if env_file:
            project_root = self.environment_config.get("project_root", ".")
            env_path = Path(project_root) / env_file
            
            if env_path.exists():
                load_dotenv(env_path)
                print(f"✅ 已加载环境变量: {env_path}")
            else:
                print(f"⚠️  环境变量文件不存在: {env_path}")
    
    def split_data(self) -> str:
        """
        切分数据文件
        
        Returns:
            切分后的目录路径
        """
        input_file = self.data_split_config.get("input_file")
        num_chunks = self.data_split_config.get("num_chunks", 100)
        output_dir = self.data_split_config.get("output_dir")
        
        if not input_file:
            raise ValueError("未配置 data_split.input_file")
        
        input_path = Path(input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_file}")
        
        self.logger.info(f"开始切分文件: {input_file}")
        self.logger.info(f"切分数量: {num_chunks} 份")
        
        # 使用 jsonl_utils 模块进行切分
        split_dir = split_jsonl(
            input_file=input_file,
            num_chunks=num_chunks,
            output_dir=output_dir
        )
        
        self.logger.info(f"✅ 切分完成: {split_dir}")
        
        return split_dir
    
    def submit_tasks(self, split_dir: str) -> Dict[str, List[Dict]]:
        """
        提交批量任务
        
        Args:
            split_dir: 切分文件目录
            
        Returns:
            各模型的提交结果
        """
        output_base_dir = self.batch_submit_config.get("output_base_dir")
        name_prefix = self.batch_submit_config.get("name_prefix", "distill")
        concurrency = self.batch_submit_config.get("concurrency", 30)
        batch_size = self.batch_submit_config.get("batch_size", 30)
        
        # SiFlow 配置
        siflow_config = self.batch_submit_config.get("siflow", {})
        count_per_pod = siflow_config.get("count_per_pod", 10)
        resource_pool = siflow_config.get("resource_pool", "eval-cpu")
        priority = siflow_config.get("priority", "medium")
        guarantee = siflow_config.get("guarantee", False)
        region = siflow_config.get("region", "cn-beijing")
        cluster = siflow_config.get("cluster", "auriga")
        
        # 是否 dry run
        dry_run = self.execution_config.get("dry_run", False)
        
        # 模型配置列表
        models = self.batch_submit_config.get("models", [])
        if not models:
            raise ValueError("未配置 batch_submit.models")
        
        # 创建批量提交器
        submitter = BatchSubmitter(region=region, cluster=cluster)
        
        all_results = {}
        
        for model_config in models:
            config_path = model_config.get("config_path")
            alias = model_config.get("alias", "default")
            
            if not config_path:
                self.logger.warning("跳过未配置 config_path 的模型")
                continue
            
            model_name = Path(config_path).stem
            task_name_prefix = f"{name_prefix}-{alias}"
            
            self.logger.info(f"\n处理模型: {model_name} (别名: {alias})")
            self.logger.info(f"配置文件: {config_path}")
            
            # 获取主任务日志目录
            task_name = self.config.get('task_name', 'unknown_task')
            logging_config = self.config.get('logging', {})
            base_log_dir = logging_config.get('log_dir', '/volume/pt-train/users/wzhang/wjj-workspace/modelcall/logs')
            subtask_log_dir = f"{base_log_dir}/{task_name}/subtasks"
            
            # 提交任务
            results = submitter.submit_distillation_tasks(
                split_dir=split_dir,
                output_base_dir=output_base_dir,
                model_config=config_path,
                name_prefix=task_name_prefix,
                concurrency=concurrency,
                batch_size=batch_size,
                count_per_pod=count_per_pod,
                resource_pool=resource_pool,
                guarantee=guarantee,
                priority=priority,
                subtask_log_dir=subtask_log_dir,
                dry_run=dry_run
            )
            
            all_results[model_name] = results
        
        return all_results
    
    def merge_results(self, model_name: str) -> dict:
        """
        合并某个模型的结果
        
        Args:
            model_name: 模型名称
            
        Returns:
            合并统计信息
        """
        output_base_dir = self.batch_submit_config.get("output_base_dir")
        post_processing = self.config.get("post_processing", {})
        
        # 构建输入输出路径
        input_dir = Path(output_base_dir) / model_name
        output_file = Path(output_base_dir) / f"{model_name}_merged.jsonl"
        
        self.logger.info(f"\n合并 {model_name} 的结果...")
        self.logger.info(f"输入目录: {input_dir}")
        self.logger.info(f"输出文件: {output_file}")
        
        if not input_dir.exists():
            self.logger.warning(f"目录不存在，跳过: {input_dir}")
            return {}
        
        # 执行合并
        merge_errors = post_processing.get("merge_errors", True)
        stats = merge_split_results(
            input_dir=str(input_dir),
            output_file=str(output_file),
            merge_errors=merge_errors
        )
        
        return stats
    
    def print_post_processing_info(self):
        """打印后处理信息"""
        output_base_dir = self.batch_submit_config.get("output_base_dir")
        models = self.batch_submit_config.get("models", [])
        post_processing = self.config.get("post_processing", {})
        
        # 检查是否启用自动合并
        auto_merge = post_processing.get("auto_merge", False)
        
        if auto_merge:
            self.logger.info("\n" + "=" * 60)
            self.logger.info("自动合并结果（任务完成后执行）")
            self.logger.info("=" * 60)
            
            for model_config in models:
                config_path = model_config.get("config_path")
                if not config_path:
                    continue
                
                model_name = Path(config_path).stem
                self.logger.info(f"\n模型: {model_name}")
                self.logger.info(f"  输入目录: {output_base_dir}/{model_name}")
                self.logger.info(f"  输出文件: {output_base_dir}/{model_name}_merged.jsonl")
        else:
            # 打印手动合并的说明
            merge_template = post_processing.get("merge_command_template", "")
            
            if merge_template:
                self.logger.info("\n" + "=" * 60)
                self.logger.info("任务完成后，可使用以下配置合并结果：")
                self.logger.info("=" * 60)
                
                for model_config in models:
                    config_path = model_config.get("config_path")
                    if not config_path:
                        continue
                    
                    model_name = Path(config_path).stem
                    
                    self.logger.info(f"\n# 合并 {model_name} 的结果:")
                    self.logger.info(f"在配置文件中设置 post_processing.auto_merge: true")
                    self.logger.info(f"或运行: python -m modelcall run-task <merge_config>.yaml")
    
    def run(self):
        """运行批量提交任务"""
        self.logger.info("=" * 60)
        self.logger.info(f"开始执行批量提交任务: {self.config.get('task_name', 'unknown')}")
        self.logger.info("=" * 60)
        
        # 步骤 1: 切分数据
        if self.execution_config.get("auto_split", True):
            self.logger.info("\n步骤 1/2: 切分数据文件")
            self.logger.info("=" * 60)
            split_dir = self.split_data()
        else:
            # 使用配置中的切分目录
            split_dir = self.data_split_config.get("output_dir")
            if not split_dir:
                input_file = self.data_split_config.get("input_file")
                split_dir = str(Path(input_file).with_suffix(""))
            
            self.logger.info(f"使用已有切分目录: {split_dir}")
        
        # 步骤 2: 批量提交任务
        self.logger.info("\n步骤 2/2: 批量提交任务")
        self.logger.info("=" * 60)
        
        all_results = self.submit_tasks(split_dir)
        
        # 统计结果
        self.logger.info("\n" + "=" * 60)
        self.logger.info("批量提交完成")
        self.logger.info("=" * 60)
        
        for model_name, results in all_results.items():
            if results:
                success_count = sum(1 for r in results if r.get("success", False))
                self.logger.info(f"\n{model_name}:")
                self.logger.info(f"  总任务数: {len(results)}")
                self.logger.info(f"  成功: {success_count}")
                self.logger.info(f"  失败: {len(results) - success_count}")
        
        # 打印后处理信息
        self.print_post_processing_info()
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info("脚本完成")
        self.logger.info("=" * 60)


"""数据蒸馏任务执行器"""

from pathlib import Path
from typing import Dict, Any

import yaml

from .base_runner import BaseTaskRunner
from ...data_distillation.chatml_converter import ChatMLConverter
from ...data_distillation.jsonl_merger import JSONLMerger
from ...data_distillation.response_generator import ResponseGenerator


class DistillationTaskRunner(BaseTaskRunner):
    """数据蒸馏任务执行器"""
    
    async def run(self, job_index: int = 0, world_size: int = 1):
        """
        运行数据蒸馏任务
        
        Args:
            job_index: 作业索引
            world_size: 作业总数
        """
        distillation_config = self.config.get("distillation")
        if not distillation_config:
            self.logger.error("数据蒸馏配置未找到")
            return
        
        step = distillation_config.get("step")
        self.logger.info(f"🔄 开始数据蒸馏步骤: {step}")
        
        if step == "chatml_conversion":
            await self._run_chatml_conversion(distillation_config)
        elif step == "jsonl_merge":
            await self._run_jsonl_merge(distillation_config)
        elif step == "generate_response":
            await self._run_generate_response(distillation_config)
        else:
            self.logger.error(f"未知的数据蒸馏步骤: {step}")
    
    async def _run_chatml_conversion(self, distillation_config: Dict[str, Any]):
        """执行ChatML格式转换"""
        self.logger.info("📝 执行ChatML格式转换...")
        
        converter = ChatMLConverter(
            dataset_config_path=distillation_config.get("dataset_config_path"),
            input_dir=distillation_config.get("input_dir"),
            output_dir=distillation_config.get("output_dir"),
            num_processes=distillation_config.get("num_processes"),
            keep_raw_data=distillation_config.get("keep_raw_data", True),
            add_system_prompt=distillation_config.get("add_system_prompt", False),
            system_prompt=distillation_config.get("system_prompt", "You are a helpful assistant and an expert coder."),
            continue_mode=distillation_config.get("continue_mode", True)
        )
        
        converter.run()
        self.logger.info("✅ ChatML格式转换完成")
    
    async def _run_jsonl_merge(self, distillation_config: Dict[str, Any]):
        """执行JSONL文件合并"""
        self.logger.info("🔗 执行JSONL文件合并...")
        
        # 加载合并配置
        merge_config_path = distillation_config.get("merge_config_path")
        with open(merge_config_path, 'r', encoding='utf-8') as f:
            merge_config = yaml.safe_load(f)
        
        base_input_dir = Path(distillation_config.get("base_input_dir"))
        base_output_dir = Path(distillation_config.get("base_output_dir"))
        chunk_size = distillation_config.get("chunk_size", 1000)
        
        # 获取要执行的合并组
        selected_groups = distillation_config.get("merge_groups", [])
        all_merge_groups = merge_config.get("merge_groups", [])
        
        # 如果没有指定或为空列表，则执行所有组
        if not selected_groups:
            groups_to_process = all_merge_groups
        else:
            # 只处理指定的组
            groups_to_process = [g for g in all_merge_groups if g["name"] in selected_groups]
        
        if not groups_to_process:
            self.logger.warning("没有找到要处理的合并组")
            return
        
        self.logger.info(f"找到 {len(groups_to_process)} 个合并组需要处理")
        
        # 逐个处理合并组
        for group in groups_to_process:
            group_name = group["name"]
            output_file = group["output_file"]
            input_files = group["input_files"]
            
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"🔄 处理合并组: {group_name}")
            self.logger.info(f"   输入文件数: {len(input_files)}")
            self.logger.info(f"   输出文件: {output_file}")
            
            # 构建完整路径
            full_input_files = [str(base_input_dir / f) for f in input_files]
            full_output_path = str(base_output_dir / output_file)
            
            # 创建合并器并执行
            merger = JSONLMerger(
                input_files=full_input_files,
                output_path=full_output_path,
                chunk_size=chunk_size
            )
            
            total = merger.run()
            self.logger.info(f"✅ 合并组 '{group_name}' 完成，共合并 {total} 条记录")
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info("✅ 所有JSONL文件合并完成")
    
    async def _run_generate_response(self, distillation_config: Dict[str, Any]):
        """执行响应生成"""
        self.logger.info("🤖 执行响应生成...")
        
        # 加载响应配置
        response_config_path = distillation_config.get("response_config_path")
        with open(response_config_path, 'r', encoding='utf-8') as f:
            response_config = yaml.safe_load(f)
        
        client_config = response_config.get("client_config", {})
        chat_config = response_config.get("chat_config", {})
        
        # 验证必需的配置
        if "model" not in chat_config:
            self.logger.error("Model name is required in chat_config")
            return
        
        input_path = distillation_config.get("input_path")
        output_path = distillation_config.get("output_path")
        concurrency = distillation_config.get("concurrency", 20)
        batch_size = distillation_config.get("batch_size", 20)
        flush_interval_secs = distillation_config.get("flush_interval_secs", 2.0)
        retry_mode = distillation_config.get("retry_mode", False)
        resume_mode = distillation_config.get("resume_mode", True)
        
        self.logger.info(f"输入文件: {input_path}")
        self.logger.info(f"输出目录: {output_path}")
        self.logger.info(f"模型: {chat_config.get('model')}")
        self.logger.info(f"并发数: {concurrency}")
        self.logger.info(f"批量大小: {batch_size}")
        self.logger.info(f"重试模式: {'启用' if retry_mode else '禁用'}")
        self.logger.info(f"断点续传: {'启用' if resume_mode else '禁用'}")
        
        # 创建响应生成器并执行
        generator = ResponseGenerator(
            input_path=input_path,
            output_path=output_path,
            client_config=client_config,
            chat_config=chat_config,
            concurrency=concurrency,
            batch_size=batch_size,
            flush_interval_secs=flush_interval_secs,
            retry_mode=retry_mode,
            resume_mode=resume_mode
        )
        
        await generator.run()
        self.logger.info("✅ 响应生成完成")


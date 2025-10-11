"""预处理任务执行器"""

import os
from pathlib import Path
from typing import Dict, Any

from .base_runner import BaseTaskRunner
from ...data_processing.preprocessors.universal import create_preprocessor_from_config
from ...data_processing.preprocessors.github_raw_code import GitHubRawCodePreprocessor
from ...data_processing.preprocessors.repo_xml import RepoXMLPreprocessor
from ...data_processing.preprocessors.triplet_filter import TripletFilterPreprocessor


class PreprocessRunner(BaseTaskRunner):
    """预处理任务执行器"""
    
    def __init__(self, config: Any, logger: Any, fs_cfg: Dict[str, Any], paths: Dict[str, str]):
        """
        初始化预处理执行器
        
        Args:
            config: 任务配置（EasyDict）
            logger: 日志管理器
            fs_cfg: 文件系统配置
            paths: 解析后的路径字典
        """
        super().__init__(config, logger, fs_cfg)
        self.paths = paths
    
    async def run(self, job_index: int = 0, world_size: int = 1):
        """
        运行预处理任务
        
        Args:
            job_index: 作业索引
            world_size: 作业总数
        """
        preprocess_config = self.config.get("preprocess")
        if not preprocess_config:
            return
        
        self.logger.info("🔧 开始数据预处理...")
        
        # 解析预处理路径
        preprocess_input = preprocess_config.get("input_folder", self.paths["input_folder"])
        preprocess_output = preprocess_config.get("output_folder", self.paths["input_folder"] + "_preprocessed")
        
        # 检查是否使用自定义脚本
        script_type = preprocess_config.get("script_type", "universal")
        
        if script_type == "github_raw_code":
            # 使用GitHub原始代码预处理脚本
            self.logger.info("🔧 使用GitHub原始代码预处理脚本")
            
            # 处理调试模式的文件限制
            debug_max_files = None
            if self.config.debug.enabled and hasattr(self.config.debug, 'max_files'):
                debug_max_files = self.config.debug.max_files
            
            num_files = debug_max_files if debug_max_files is not None else preprocess_config.get("num_files", -1)
            
            preprocessor = GitHubRawCodePreprocessor(
                raw_path=preprocess_input,
                output_dir=preprocess_output.replace("tos://agi-data/", ""),  # 移除前缀
                stat_dir=os.path.join(self.paths["stat_folder"], "preprocess"),
                fs_cfg=self.fs_cfg,
                max_tokens=preprocess_config.get("max_tokens", 32768),
                num_proc=preprocess_config.get("num_proc", 32),
                seed=preprocess_config.get("seed", 42),
                num_files=num_files,
                batch_size=preprocess_config.get("batch_size", 1000)
            )
            
            # 运行预处理
            preprocessor.run()
            
        elif script_type == "repo_xml":
            # 使用代码仓库XML/CXML预处理脚本
            self.logger.info("🔧 使用代码仓库XML/CXML预处理脚本")
            
            # 处理调试模式的文件限制
            debug_max_files = None
            if self.config.debug.enabled and hasattr(self.config.debug, 'max_files'):
                debug_max_files = self.config.debug.max_files
            
            num_files = debug_max_files if debug_max_files is not None else preprocess_config.get("num_files", -1)
            
            preprocessor = RepoXMLPreprocessor(
                raw_path=preprocess_input,
                output_dir=preprocess_output.replace("tos://agi-data/", ""),  # 移除前缀
                stat_dir=os.path.join(self.paths["stat_folder"], "preprocess"),
                fs_cfg=self.fs_cfg,
                max_tokens=preprocess_config.get("max_tokens", 32768),
                num_proc=preprocess_config.get("num_proc", 16),
                seed=preprocess_config.get("seed", 42),
                num_files=num_files,
                languages=preprocess_config.get("languages"),
                batch_size=preprocess_config.get("batch_size", 1000)
            )
            
            # 运行预处理
            preprocessor.run()
            
        else:
            # 使用通用预处理器
            self.logger.info("🔧 使用通用预处理器")
            
            # 添加TOS前缀
            if not preprocess_input.startswith(("tos://", "/", ".")):
                preprocess_input = f"tos://agi-data/{preprocess_input}"
            if not preprocess_output.startswith(("tos://", "/", ".")):
                preprocess_output = f"tos://agi-data/{preprocess_output}"
            
            # 创建预处理器
            if script_type == "triplet_filter":
                preprocessor = TripletFilterPreprocessor(
                    raw_path=preprocess_input,
                    output_dir=preprocess_output,
                    stat_dir=os.path.join(self.paths["stat_folder"], "preprocess"),
                    fs_cfg=self.fs_cfg,
                    max_tokens=preprocess_config.get("max_tokens", 32768),
                    num_proc=preprocess_config.get("num_proc", 16),
                    batch_size=preprocess_config.get("batch_size", 1000),
                    group_by_language=preprocess_config.get("group_by_language", True)
                )
            else:
                # 使用通用预处理器
                preprocessor = create_preprocessor_from_config(
                    preprocess_config=preprocess_config,
                    raw_path=preprocess_input,
                    output_dir=preprocess_output,
                    stat_dir=os.path.join(self.paths["stat_folder"], "preprocess"),
                    fs_cfg=self.fs_cfg,
                    max_tokens=preprocess_config.get("max_tokens", 32768),
                    num_proc=preprocess_config.get("num_proc", 32)
                )
            
            # 运行预处理
            preprocessor.run()
        
        self.logger.info("✅ 数据预处理完成")
        
        # 更新任务配置中的输入路径为预处理后的路径
        # 保持预处理输出路径的原始格式（本地/TOS）
        self.config.data.input_folder = preprocess_output
        
        return preprocess_output


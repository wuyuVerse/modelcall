"""通用数据预处理器 - 将各种数据源统一为标准格式"""

from __future__ import annotations

import os
import json
import copy
from uuid import uuid4
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

from .base import BasePreprocessor
from ..utils import process_text
from ..logging_manager import get_logger

import tiktoken


class UniversalPreprocessor(BasePreprocessor):
    """通用预处理器，支持多种数据源格式转换"""
    
    def __init__(self, 
                 raw_path: str,
                 output_dir: str,
                 stat_dir: str,
                 fs_cfg: Dict[str, Any],
                 preprocess_config: Dict[str, Any],
                 max_tokens: int = 32768,
                 num_proc: int = 32):
        
        super().__init__(raw_path, output_dir, stat_dir, fs_cfg, max_tokens, num_proc)
        
        self.preprocess_config = preprocess_config
        self.source_name = preprocess_config.get("source_name", "unknown")
        
        # 字段映射配置
        self.field_mapping = preprocess_config.get("field_mapping", {})
        
        # 数据过滤和处理配置
        self.filters = preprocess_config.get("filters", {})
        self.transformations = preprocess_config.get("transformations", {})
        
        # 获取logger
        self.logger = get_logger()
    
    def get_file_list(self) -> List[tuple[str, str]]:
        """获取要处理的文件列表"""
        from ..fs.tos import TOSFileSystem
        from ..fs.local import LocalFileSystem
        from ..fs.base import FSConfig
        
        # 根据路径类型选择文件系统
        if self.raw_path.startswith("tos://"):
            tos_config = self.fs_cfg.get("tos", {})
            config = FSConfig(
                bucket=tos_config.get("bucket", "agi-data"),
                endpoint=tos_config.get("endpoint"),
                root=tos_config.get("prefix")
            )
            fs = TOSFileSystem(config)
            
            # 处理TOS路径
            if self.raw_path.startswith("tos://agi-data/"):
                search_path = self.raw_path
            else:
                search_path = f"tos://agi-data/{self.raw_path}"
            
            file_pattern = self.preprocess_config.get("file_pattern", "*.parquet")
            file_names = fs.glob(os.path.join(search_path, file_pattern))
            
            all_input_files = []
            all_output_files = []
            
            for file_path in file_names:
                input_file = f"tos://{file_path}" if not file_path.startswith("tos://") else file_path
                output_file = os.path.join(f"tos://agi-data/{self.output_dir}", 
                                         os.path.basename(file_path))
                all_input_files.append(input_file)
                all_output_files.append(output_file)
            
        else:
            # 本地文件系统
            fs = LocalFileSystem()
            input_path = Path(self.raw_path)
            
            file_pattern = self.preprocess_config.get("file_pattern", "*.parquet")
            files = list(input_path.glob(file_pattern))
            
            all_input_files = []
            all_output_files = []
            
            for file_path in files:
                output_file = os.path.join(self.output_dir, file_path.name)
                all_input_files.append(str(file_path))
                all_output_files.append(output_file)
        
        return list(zip(all_input_files, all_output_files))
    
    def process_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理单个数据项，转换为统一格式"""
        try:
            # 应用字段映射
            mapped_item = self._apply_field_mapping(item)
            
            # 应用过滤器
            if not self._apply_filters(mapped_item):
                return None
            
            # 应用转换
            transformed_item = self._apply_transformations(mapped_item)
            
            # 确保必需字段存在
            result = self._ensure_required_fields(transformed_item)
            
            # 处理文本截断
            if "text" in result and result["text"]:
                processed_text = process_text(result["text"], self.enc, self.max_tokens)
                result[f'content_truncate_{self.max_tokens//1024}k'] = processed_text
            
            return result
            
        except Exception as e:
            if self.logger:
                self.logger.warning(f"处理项目失败: {e}")
            return None
    
    def _apply_field_mapping(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """应用字段映射"""
        if not self.field_mapping:
            return item
        
        mapped = {}
        
        # 映射已配置的字段
        for target_field, source_field in self.field_mapping.items():
            if isinstance(source_field, str):
                # 简单字段映射
                if source_field in item:
                    mapped[target_field] = item[source_field]
            elif isinstance(source_field, dict):
                # 复杂映射（如组合字段）
                if source_field.get("type") == "combine":
                    # 组合多个字段
                    fields = source_field.get("fields", [])
                    separator = source_field.get("separator", " ")
                    values = []
                    for field in fields:
                        if field in item and item[field]:
                            values.append(str(item[field]))
                    mapped[target_field] = separator.join(values)
                elif source_field.get("type") == "constant":
                    # 常量值
                    mapped[target_field] = source_field.get("value", "")
        
        # 保留未映射的字段
        for key, value in item.items():
            if key not in mapped:
                mapped[key] = value
        
        return mapped
    
    def _apply_filters(self, item: Dict[str, Any]) -> bool:
        """应用过滤器"""
        if not self.filters:
            return True
        
        # 最小长度过滤
        min_length = self.filters.get("min_text_length")
        if min_length and "text" in item:
            if len(str(item["text"])) < min_length:
                return False
        
        # 最大长度过滤
        max_length = self.filters.get("max_text_length")
        if max_length and "text" in item:
            if len(str(item["text"])) > max_length:
                return False
        
        # 必需字段过滤
        required_fields = self.filters.get("required_fields", [])
        for field in required_fields:
            if field not in item or not item[field]:
                return False
        
        # 黑名单过滤
        blacklist_patterns = self.filters.get("blacklist_patterns", [])
        text_content = str(item.get("text", "")).lower()
        for pattern in blacklist_patterns:
            if pattern.lower() in text_content:
                return False
        
        return True
    
    def _apply_transformations(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """应用数据转换"""
        result = copy.deepcopy(item)
        
        if not self.transformations:
            return result
        
        # 文本清理
        text_cleaning = self.transformations.get("text_cleaning", {})
        if text_cleaning and "text" in result:
            text = str(result["text"])
            
            # 移除多余空白
            if text_cleaning.get("remove_extra_whitespace", False):
                import re
                text = re.sub(r'\s+', ' ', text).strip()
            
            # 移除特殊字符
            remove_chars = text_cleaning.get("remove_characters", [])
            for char in remove_chars:
                text = text.replace(char, "")
            
            result["text"] = text
        
        # 添加计算字段
        computed_fields = self.transformations.get("computed_fields", {})
        for field_name, computation in computed_fields.items():
            if computation["type"] == "text_length":
                source_field = computation.get("source_field", "text")
                if source_field in result:
                    result[field_name] = len(str(result[source_field]))
            elif computation["type"] == "token_count":
                source_field = computation.get("source_field", "text")
                if source_field in result:
                    tokens = self.enc.encode(str(result[source_field]), disallowed_special=())
                    result[field_name] = len(tokens)
        
        return result
    
    def _ensure_required_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """确保必需字段存在"""
        result = copy.deepcopy(item)
        
        # 确保有ID
        if 'id' not in result or not result['id']:
            result['id'] = str(uuid4())
        
        # 确保有text字段
        if 'text' not in result:
            # 尝试从其他字段获取
            text_candidates = ['content', 'body', 'description', 'message']
            for candidate in text_candidates:
                if candidate in result and result[candidate]:
                    result['text'] = str(result[candidate])
                    break
            else:
                result['text'] = ""
        
        # 确保有source字段
        if 'source' not in result:
            result['source'] = self.source_name
        
        return result


def create_preprocessor_from_config(preprocess_config: Dict[str, Any], 
                                  raw_path: str,
                                  output_dir: str, 
                                  stat_dir: str,
                                  fs_cfg: Dict[str, Any],
                                  max_tokens: int = 32768,
                                  num_proc: int = 32) -> UniversalPreprocessor:
    """从配置创建预处理器"""
    
    return UniversalPreprocessor(
        raw_path=raw_path,
        output_dir=output_dir,
        stat_dir=stat_dir,
        fs_cfg=fs_cfg,
        preprocess_config=preprocess_config,
        max_tokens=max_tokens,
        num_proc=num_proc
    )

"""ChatML格式转换器 - 将各种数据集格式转换为ChatML格式"""

import json
import logging
from functools import partial
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Dict, Any, Optional, List

from datasets import load_dataset, get_dataset_split_names
from tqdm import tqdm
import yaml


class ChatMLConverter:
    """ChatML格式转换器"""
    
    def __init__(
        self,
        dataset_config_path: str,
        input_dir: str,
        output_dir: str,
        num_processes: int = None,
        keep_raw_data: bool = True,
        add_system_prompt: bool = False,
        system_prompt: str = "You are a helpful assistant and an expert coder.",
        continue_mode: bool = True,
        selected_datasets: Optional[List[str]] = None
    ):
        """
        初始化ChatML转换器
        
        Args:
            dataset_config_path: 数据集配置文件路径
            input_dir: 输入数据集目录
            output_dir: 输出目录
            num_processes: 并行处理进程数
            keep_raw_data: 是否保留原始数据
            add_system_prompt: 是否添加system prompt
            system_prompt: system prompt内容
            continue_mode: 是否跳过已存在的文件
        """
        self.dataset_config = self._load_dataset_config(dataset_config_path)
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.num_processes = num_processes or cpu_count()
        self.keep_raw_data = keep_raw_data
        self.add_system_prompt = add_system_prompt
        self.system_prompt = system_prompt
        self.continue_mode = continue_mode
        self.selected_datasets = set(selected_datasets) if selected_datasets else None
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置日志
        self.logger = logging.getLogger(__name__)
    
    def _load_dataset_config(self, config_path: str) -> Dict[str, Dict[str, Any]]:
        """加载数据集配置"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    # ==================================================================================================
    # FORMATTING FUNCTIONS - 保持原始逻辑不变
    # ==================================================================================================
    
    @staticmethod
    def create_chatml_structure(
        messages: list, 
        original_sample: Dict,
        keep_raw_data: bool,
        add_system_prompt: bool, 
        system_prompt: str
    ) -> Dict[str, Any]:
        """根据消息列表创建最终的ChatML字典"""
        if not messages:
            return {}
        
        final_messages = messages
        if add_system_prompt and not any(m['role'] == 'system' for m in messages):
            final_messages = [{"role": "system", "content": system_prompt}] + messages
        
        output_dict = {
            "messages": final_messages,
            "format": "chatml"
        }
        
        if keep_raw_data:
            # 确保原始数据可以被JSON序列化
            output_dict["raw_data"] = {k: repr(v) if isinstance(v, bytes) else v for k, v in original_sample.items()}
            
        return output_dict
    
    @staticmethod
    def format_prompt_response(sample: Dict, mapping: Dict, **kwargs) -> Optional[Dict]:
        """格式化 prompt-response 格式"""
        prompt = sample.get(mapping["prompt"])
        response = sample.get(mapping["response"])
        if not prompt or not response:
            return None
        messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": response}]
        return ChatMLConverter.create_chatml_structure(messages, original_sample=sample, **kwargs)
    
    @staticmethod
    def format_instruction_input(sample: Dict, mapping: Dict, **kwargs) -> Optional[Dict]:
        """格式化 instruction-input 格式"""
        instruction = sample.get(mapping["prompt"])
        inp = sample.get(mapping["input"], "")
        response = sample.get(mapping["response"])
        if not instruction or not response:
            return None
        prompt = f"{instruction}\n\n{inp}".strip() if inp else instruction
        messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": response}]
        return ChatMLConverter.create_chatml_structure(messages, original_sample=sample, **kwargs)
    
    @staticmethod
    def format_sharegpt(sample: Dict, mapping: Dict, **kwargs) -> Optional[Dict]:
        """格式化 ShareGPT 格式"""
        conversations = sample.get(mapping["conversations"], [])
        if not conversations:
            return None
        role_mapping = {"human": "user", "gpt": "assistant", "user": "user", "assistant": "assistant"}
        messages = []
        for turn in conversations:
            role = role_mapping.get(turn.get("from"))
            content = turn.get("value")
            if role and content:
                messages.append({"role": role, "content": content})
        return ChatMLConverter.create_chatml_structure(messages, original_sample=sample, **kwargs)
    
    @staticmethod
    def format_messages(sample: Dict, mapping: Dict, **kwargs) -> Optional[Dict]:
        """格式化标准 messages 格式"""
        messages = sample.get(mapping["messages"], [])
        return ChatMLConverter.create_chatml_structure(messages, original_sample=sample, **kwargs)
    
    @staticmethod
    def format_input_output_messages(sample: Dict, mapping: Dict, **kwargs) -> Optional[Dict]:
        """处理 input 是 messages 列表，output 是字符串的格式"""
        input_messages = sample.get(mapping["input"], [])
        output = sample.get(mapping["output"])
        if not input_messages or not output:
            return None
        # 将 output 作为 assistant 的回复添加到 messages 中
        messages = input_messages + [{"role": "assistant", "content": output}]
        return ChatMLConverter.create_chatml_structure(messages, original_sample=sample, **kwargs)
    
    @staticmethod
    def format_prompt_text_only(sample: Dict, mapping: Dict, **kwargs) -> Optional[Dict]:
        """格式化只有 prompt_text 字段的格式（如 oo1.jsonl）"""
        prompt_text = sample.get(mapping["prompt_text"])
        if not prompt_text:
            return None
        messages = [{"role": "user", "content": prompt_text}]
        return ChatMLConverter.create_chatml_structure(messages, original_sample=sample, **kwargs)
    
    def _get_formatters(self) -> Dict:
        """获取格式化函数映射"""
        return {
            "prompt_response": self.format_prompt_response,
            "instruction_input": self.format_instruction_input,
            "sharegpt": self.format_sharegpt,
            "messages": self.format_messages,
            "input_output_messages": self.format_input_output_messages,
            "prompt_text_only": self.format_prompt_text_only,
        }
    
    # ==================================================================================================
    # PROCESSING LOGIC - 保持原始逻辑不变
    # ==================================================================================================
    
    def process_single_task(self, task_info: tuple) -> None:
        """处理单个数据集配置和切片的worker函数"""
        dataset_key, config_name, split, input_dir, output_dir = task_info
        
        try:
            config_details = self.dataset_config[dataset_key]
            mapping = config_details["column_mapping"]
            formatters = self._get_formatters()
            formatter = formatters[config_details["format_style"]]
            
            dataset_path = Path(input_dir) / dataset_key
            # 兼容 input_dir 直接指向数据集叶子目录的情况：
            # 例如 input_dir = "/.../nvidia/Nemotron-Post-Training-Dataset-v2",
            # 而 dataset_key = "nvidia/Nemotron-Post-Training-Dataset-v2"
            if not dataset_path.exists():
                leaf_dir = Path(input_dir)
                if leaf_dir.exists() and leaf_dir.name == Path(dataset_key).name:
                    dataset_path = leaf_dir
            
            # 判断是否为纯 JSONL 文件（通过检查路径是否为文件）
            is_jsonl_file = dataset_path.is_file() and dataset_path.suffix == '.jsonl'
            
            if is_jsonl_file:
                # 纯 JSONL 文件：使用 'json' 格式加载
                dataset = load_dataset('json', data_files=str(dataset_path), split='train')
            else:
                # HuggingFace datasets 目录格式
                # 本地目录存在：不传 trust_remote_code；远端数据集：需要 trust_remote_code
                if dataset_path.exists():
                    dataset = load_dataset(str(dataset_path), name=config_name, split=split)
                else:
                    dataset = load_dataset(dataset_key, name=config_name, split=split, trust_remote_code=True)
            
            # 输出目录：按数据集名分子目录（例如 prepared/Nemotron-Post-Training-Dataset-v2）
            dataset_dir_name = Path(dataset_key).name
            if is_jsonl_file and dataset_dir_name.endswith('.jsonl'):
                dataset_dir_name = dataset_dir_name[:-6]
            dataset_output_dir = Path(output_dir) / dataset_dir_name
            dataset_output_dir.mkdir(parents=True, exist_ok=True)

            # 文件名键：与 run() 中的 continue 判断保持一致（JSONL 去除扩展名）
            config_str = f"-{config_name}" if config_name else ""
            if is_jsonl_file:
                file_name_key = dataset_key.replace("/", "_").replace(".jsonl", "")
            else:
                file_name_key = dataset_key.replace("/", "_")

            if self.add_system_prompt:
                output_file_path = dataset_output_dir / f"{file_name_key}{config_str}-{split}-with_system.jsonl"
            else:
                output_file_path = dataset_output_dir / f"{file_name_key}{config_str}-{split}.jsonl"
            
            formatter_kwargs = {
                "keep_raw_data": self.keep_raw_data,
                "add_system_prompt": self.add_system_prompt,
                "system_prompt": self.system_prompt
            }
            
            with open(output_file_path, "w", encoding="utf-8") as f:
                for sample in tqdm(dataset, desc=f"Converting {dataset_key} ({config_name or 'default'}) [{split}]"):
                    chatml_sample = formatter(sample, mapping, **formatter_kwargs)
                    if chatml_sample and chatml_sample.get("messages"):
                        f.write(json.dumps(chatml_sample, ensure_ascii=False) + "\n")
                        
            self.logger.info(f"Successfully converted {dataset_key} ({config_name or 'default'}) [{split}]")

        except Exception as e:
            self.logger.error(f"Failed to process {dataset_key} ({config_name or 'default'}) [{split}]: {e}", exc_info=False)
    
    def run(self) -> None:
        """运行转换任务"""
        tasks_to_run = []
        skipped_count = 0
        
        # 如果指定了 selected_datasets，则只处理这些数据集
        if self.selected_datasets is not None:
            dataset_items = [(k, v) for k, v in self.dataset_config.items() if k in self.selected_datasets]
            missing = [k for k in self.selected_datasets if k not in self.dataset_config]
            if missing:
                self.logger.warning(f"Selected datasets not found in config and will be ignored: {missing}")
            self.logger.info(f"Limiting processing to {len(dataset_items)} selected dataset(s)")
        else:
            dataset_items = list(self.dataset_config.items())

        for dataset_key, config_details in dataset_items:
            dataset_path = self.input_dir / dataset_key
            if not dataset_path.exists():
                # 兼容 input_dir 直接指向数据集叶子目录的情况
                leaf_dir = self.input_dir
                if leaf_dir.exists() and leaf_dir.name == Path(dataset_key).name:
                    dataset_path = leaf_dir
                else:
                    self.logger.warning(f"Dataset path not found, skipping: {dataset_path}")
                    continue

            # 判断是否为纯 JSONL 文件
            is_jsonl_file = dataset_path.is_file() and dataset_path.suffix == '.jsonl'
            
            if is_jsonl_file:
                # 纯 JSONL 文件：只有一个 "train" split
                file_name_key = dataset_key.replace("/", "_").replace(".jsonl", "")
                dataset_dir_name = Path(dataset_key).name
                if dataset_dir_name.endswith('.jsonl'):
                    dataset_dir_name = dataset_dir_name[:-6]
                per_dataset_dir = self.output_dir / dataset_dir_name
                per_dataset_dir.mkdir(parents=True, exist_ok=True)
                if self.add_system_prompt:
                    output_file_path = per_dataset_dir / f"{file_name_key}-train-with_system.jsonl"
                else:
                    output_file_path = per_dataset_dir / f"{file_name_key}-train.jsonl"
                
                if self.continue_mode and output_file_path.exists():
                    self.logger.info(f"Skipping task for '{output_file_path.name}' as it already exists.")
                    skipped_count += 1
                else:
                    tasks_to_run.append((dataset_key, None, 'train', str(self.input_dir), str(self.output_dir)))
            else:
                # HuggingFace datasets 目录格式
                configs_to_process = config_details.get("configs", [None])
                for config_name in configs_to_process:
                    try:
                        # 本地目录存在：不传 trust_remote_code；远端数据集：需要 trust_remote_code
                        if dataset_path.exists():
                            try:
                                split_names = get_dataset_split_names(str(dataset_path), config_name=config_name)
                            except Exception:
                                split_names = ["train"]
                        else:
                            try:
                                split_names = get_dataset_split_names(dataset_key, config_name=config_name, trust_remote_code=True)
                            except Exception:
                                split_names = ["train"]
                        for split in split_names:
                            # 检查文件是否存在于 continue_mode
                            config_str = f"-{config_name}" if config_name else ""
                            file_name_key = dataset_key.replace("/", "_")
                            dataset_dir_name = Path(dataset_key).name
                            per_dataset_dir = self.output_dir / dataset_dir_name
                            per_dataset_dir.mkdir(parents=True, exist_ok=True)
                            if self.add_system_prompt:
                                output_file_path = per_dataset_dir / f"{file_name_key}{config_str}-{split}-with_system.jsonl"    
                            else:
                                output_file_path = per_dataset_dir / f"{file_name_key}{config_str}-{split}.jsonl"

                            if self.continue_mode and output_file_path.exists():
                                self.logger.info(f"Skipping task for '{output_file_path.name}' as it already exists.")
                                skipped_count += 1
                                continue  # 跳过此任务
                            
                            tasks_to_run.append((dataset_key, config_name, split, str(self.input_dir), str(self.output_dir)))
                    except Exception as e:
                        self.logger.error(f"Could not get splits for {dataset_key} (config: {config_name}). Error: {e}")

        if skipped_count > 0:
            self.logger.info(f"Skipped {skipped_count} tasks that were already completed (continue_mode).")

        if not tasks_to_run:
            self.logger.info("No new tasks to run. All configured datasets are either processed or not found.")
            self.logger.info(f"DEBUG: Total datasets in config: {len(self.dataset_config)}")
            return
            
        self.logger.info(f"Found {len(tasks_to_run)} new tasks to process.")
        self.logger.info(f"DEBUG: First 3 tasks: {tasks_to_run[:3]}")
        
        worker_func = partial(self.process_single_task)

        with Pool(self.num_processes) as pool:
            list(tqdm(pool.imap(worker_func, tasks_to_run), total=len(tasks_to_run), desc="Overall Progress"))

        self.logger.info("\nAll processing tasks complete.")


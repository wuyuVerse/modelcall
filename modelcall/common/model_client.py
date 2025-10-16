"""统一的模型客户端 - 支持数据评分和数据蒸馏的API调用"""

import os
import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

import yaml
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


class UnifiedModelClient:
    """统一的异步模型客户端，支持多种配置方式"""
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[str] = None,
        use_env: bool = False,
        max_concurrent_requests: int = 10,
        timeout: int = 600,
        max_retries: int = 3
    ):
        """
        初始化模型客户端
        
        Args:
            config: 直接传入的配置字典，格式：{"client_config": {...}, "chat_config": {...}}
            config_path: 配置文件路径（YAML或JSON）
            use_env: 是否使用环境变量（BASE_URL, API_KEY）
            max_concurrent_requests: 最大并发请求数
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.max_concurrent_requests = max_concurrent_requests
        self.default_timeout = timeout
        self.default_max_retries = max_retries
        
        # 加载配置
        if config:
            self.client_config = config.get("client_config", {})
            self.chat_config = config.get("chat_config", {})
        elif config_path:
            loaded_config = self._load_config_file(config_path)
            self.client_config = loaded_config.get("client_config", {})
            self.chat_config = loaded_config.get("chat_config", {})
        elif use_env:
            self.client_config = {
                "base_url": os.environ.get("BASE_URL", "https://api.openai.com/v1"),
                "api_key": os.environ.get("API_KEY", ""),
                "timeout": int(os.environ.get("TIMEOUT", str(timeout))),
                "max_retries": int(os.environ.get("MAX_RETRIES", str(max_retries)))
            }
            self.chat_config = {
                "model": os.environ.get("MODEL_NAME", "gpt-3.5-turbo"),
                "temperature": float(os.environ.get("TEMPERATURE", "0.7")),
                "max_tokens": int(os.environ.get("MAX_TOKENS", "4000"))
            }
        else:
            raise ValueError("必须提供 config、config_path 或 use_env 之一")
        
        # 验证必需配置
        if not self.client_config.get("api_key"):
            raise ValueError("API key is required")
        if not self.chat_config.get("model"):
            raise ValueError("Model name is required")
        
        # 初始化客户端
        self.client = self._init_client()
        
        # 并发控制
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
    
    def _load_config_file(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件（支持YAML和JSON）"""
        config_path = Path(config_path)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.suffix in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            elif config_path.suffix == '.json':
                return json.load(f)
            else:
                raise ValueError(f"不支持的配置文件格式: {config_path.suffix}")
    
    def _init_client(self) -> AsyncOpenAI:
        """初始化 OpenAI 客户端"""
        return AsyncOpenAI(
            base_url=self.client_config.get("base_url", "https://api.openai.com/v1"),
            api_key=self.client_config["api_key"],
            timeout=self.client_config.get("timeout", self.default_timeout),
            max_retries=self.client_config.get("max_retries", self.default_max_retries)
        )
    
    async def _chat_completion_raw(
        self, 
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """原始的聊天补全请求（无重试）"""
        async with self.semaphore:
            # 合并配置参数
            chat_params = {**self.chat_config, **kwargs}
            chat_params["messages"] = messages
            
            # 移除不是 API 参数的配置
            timeout = chat_params.pop("timeout", self.client_config.get("timeout", self.default_timeout))
            # 兼容 reasoning 参数：
            # - OpenAI Responses: reasoning = {effort: ...}
            # - GPT-OSS: reasoning_effort = "low|medium|high"
            # 通过 extra_body 传递，避免 SDK 参数校验报错
            extra_body = {}
            if "reasoning" in chat_params:
                extra_body["reasoning"] = chat_params.pop("reasoning")
            if "reasoning_effort" in chat_params:
                extra_body["reasoning_effort"] = chat_params.pop("reasoning_effort")
            
            if extra_body:
                response = await self.client.chat.completions.create(**chat_params, extra_body=extra_body)
            else:
                response = await self.client.chat.completions.create(**chat_params)
            
            # 处理响应内容
            content = ""
            reasoning_content = ""
            
            # 处理流式响应
            if chat_params.get("stream", False):
                async for chunk in response:
                    if hasattr(chunk, "choices") and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, "content") and delta.content:
                            content += delta.content
                        # 兼容字段：reasoning_content 或 reasoning（GPT-OSS）
                        if hasattr(delta, "reasoning_content") and getattr(delta, "reasoning_content"):
                            reasoning_content += delta.reasoning_content
                        elif hasattr(delta, "reasoning") and getattr(delta, "reasoning"):
                            # reasoning 可能是字符串增量，这里直接拼接
                            reasoning_content += delta.reasoning
            else:
                # 非流式响应
                if hasattr(response, "choices") and len(response.choices) > 0:
                    message = response.choices[0].message
                    # 同时读取 content 与 reasoning/reasoning_content（不能用 elif）
                    if hasattr(message, "content") and message.content:
                        content = message.content
                    if hasattr(message, "reasoning_content") and message.reasoning_content:
                        reasoning_content = message.reasoning_content
                    # GPT-OSS 返回 message.reasoning
                    if hasattr(message, "reasoning") and message.reasoning and not reasoning_content:
                        reasoning_content = message.reasoning
            
            # 组合思维链和内容
            if reasoning_content and reasoning_content.strip():
                return f"<think>\n{reasoning_content}\n</think>\n\n{content}"
            else:
                return content if content else reasoning_content
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=5, min=4, max=60))
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """
        聊天补全请求（带重试）
        
        Args:
            messages: 消息列表
            **kwargs: 额外的聊天参数（会覆盖默认配置）
        
        Returns:
            str: 模型响应内容
        """
        try:
            return await self._chat_completion_raw(messages, **kwargs)
        except Exception as e:
            print(f"🔄 API调用失败，重试中: {type(e).__name__} - {str(e)}")
            raise
    
    async def batch_chat_completion(
        self,
        messages_list: List[List[Dict[str, str]]],
        **kwargs
    ) -> List[str]:
        """
        批量聊天补全请求
        
        Args:
            messages_list: 消息列表的列表
            **kwargs: 额外的聊天参数
        
        Returns:
            List[str]: 模型响应内容列表
        """
        tasks = [
            self.chat_completion(messages, **kwargs)
            for messages in messages_list
        ]
        return await asyncio.gather(*tasks)
    
    def get_chat_config(self) -> Dict[str, Any]:
        """获取当前的聊天配置"""
        return self.chat_config.copy()
    
    def get_client_config(self) -> Dict[str, Any]:
        """获取当前的客户端配置（隐藏API密钥）"""
        config = self.client_config.copy()
        if "api_key" in config:
            config["api_key"] = "***" + config["api_key"][-4:] if len(config["api_key"]) > 4 else "***"
        return config


class ModelClientFactory:
    """模型客户端工厂类"""
    
    @staticmethod
    def from_config_file(config_path: str, **kwargs) -> UnifiedModelClient:
        """从配置文件创建客户端"""
        return UnifiedModelClient(config_path=config_path, **kwargs)
    
    @staticmethod
    def from_config_dict(config: Dict[str, Any], **kwargs) -> UnifiedModelClient:
        """从配置字典创建客户端"""
        return UnifiedModelClient(config=config, **kwargs)
    
    @staticmethod
    def from_env(**kwargs) -> UnifiedModelClient:
        """从环境变量创建客户端"""
        return UnifiedModelClient(use_env=True, **kwargs)
    
    @staticmethod
    def from_task_config(task_config: Dict[str, Any], **kwargs) -> UnifiedModelClient:
        """
        从任务配置创建客户端
        
        Args:
            task_config: 任务配置字典，可以包含：
                - model_config_path: 模型配置文件路径
                - model_config: 模型配置字典
                - 或直接包含 client_config 和 chat_config
        """
        # 优先级：直接配置 > model_config > model_config_path > 环境变量
        if "client_config" in task_config and "chat_config" in task_config:
            return UnifiedModelClient(config=task_config, **kwargs)
        elif "model_config" in task_config:
            return UnifiedModelClient(config=task_config["model_config"], **kwargs)
        elif "model_config_path" in task_config:
            return UnifiedModelClient(config_path=task_config["model_config_path"], **kwargs)
        else:
            # 回退到环境变量
            return UnifiedModelClient(use_env=True, **kwargs)


def save_model_config(config: Dict[str, Any], output_path: str) -> None:
    """
    保存模型配置到文件
    
    Args:
        config: 配置字典
        output_path: 输出路径（.yaml 或 .json）
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        if output_path.suffix in ['.yaml', '.yml']:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        elif output_path.suffix == '.json':
            json.dump(config, f, ensure_ascii=False, indent=2)
        else:
            raise ValueError(f"不支持的文件格式: {output_path.suffix}")
    
    print(f"✅ 配置已保存到: {output_path}")


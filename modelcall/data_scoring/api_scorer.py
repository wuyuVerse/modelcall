"""API-based scorer with concurrent request handling."""

from __future__ import annotations

import os
import asyncio
import json
import copy
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

import yaml
from easydict import EasyDict
from tenacity import retry, stop_after_attempt, wait_exponential

from ..common.model_client import UnifiedModelClient


# 允许从配置覆盖的聊天参数（不包括 model 和 stream）
ALLOWED_CHAT_PARAMS = {
    'temperature', 'max_tokens', 'top_p', 
    'frequency_penalty', 'presence_penalty', 'stop'
}


class APIScorer:
    """API-based scorer supporting various model providers."""
    
    def __init__(self, 
                 model_config_path: str,
                 prompt_config_path: str,
                 max_concurrent_requests: int = 10,
                 max_retries: int = 3,
                 request_timeout: int = 120,
                 enable_format_validation_retry: bool = True):
        
        self.max_concurrent_requests = max_concurrent_requests
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        self.enable_format_validation_retry = enable_format_validation_retry
        
        # Load configurations
        self.model_config = self._load_config(model_config_path)
        self.prompt_config = self._load_config(prompt_config_path)
        
        # 提取模型名称（支持新旧两种格式）
        if "chat_config" in self.model_config:
            self.model_name = self.model_config.chat_config.get("model")
            # 只允许特定的参数覆盖，避免冲突（如 stream）
            self.chat_params = {
                k: v for k, v in self.model_config.chat_config.items() 
                if k in ALLOWED_CHAT_PARAMS
            }
        else:
            # 向后兼容旧格式
            self.model_name = self.model_config.get("model_name")
            self.chat_params = self.model_config.get("completions_params", {})
        
        if not self.model_name:
            raise ValueError("模型名称未找到。请在 model_config 中提供 chat_config.model 或 model_name")
        
        # Initialize API client (包含并发控制)
        self.client = self._init_client()
    
    def _load_config(self, config_path: str) -> EasyDict:
        """Load YAML configuration file."""
        with open(config_path, 'r', encoding='utf-8') as f:
            return EasyDict(yaml.safe_load(f))
    
    def _init_client(self) -> UnifiedModelClient:
        """Initialize unified model client.
        
        优先级：
        1. model_config 中的统一配置格式（client_config + chat_config）
        2. 环境变量 BASE_URL 和 API_KEY（向后兼容）
        """
        # 尝试使用统一配置格式
        if "client_config" in self.model_config and "chat_config" in self.model_config:
            config = {
                "client_config": dict(self.model_config.client_config),
                "chat_config": dict(self.model_config.chat_config)
            }
            
            # 从 client_config 更新超时和重试配置
            client_cfg = self.model_config.client_config
            if "timeout" in client_cfg:
                self.request_timeout = client_cfg.get("timeout", self.request_timeout)
            if "max_retries" in client_cfg:
                self.max_retries = client_cfg.get("max_retries", self.max_retries)
            
            return UnifiedModelClient(
                config=config,
                max_concurrent_requests=self.max_concurrent_requests,  # 由 UnifiedModelClient 统一控制并发
                timeout=self.request_timeout,
                max_retries=self.max_retries
            )
        
        # 回退到环境变量（向后兼容）
        if os.environ.get("BASE_URL") or os.environ.get("API_KEY"):
            return UnifiedModelClient(
                use_env=True,
                max_concurrent_requests=self.max_concurrent_requests,  # 由 UnifiedModelClient 统一控制并发
                timeout=self.request_timeout,
                max_retries=self.max_retries
            )
        
        raise ValueError(
            "API配置未找到。请在 model_config 中提供统一格式配置"
            "（client_config + chat_config），或设置环境变量 BASE_URL 和 API_KEY"
        )
    
    async def _get_chat_completion_raw(self, message: List[Dict[str, str]]) -> str:
        """Get raw completion from API without retry logic.
        
        并发控制由 UnifiedModelClient 内部管理。
        """
        # 直接调用统一客户端（内部已有并发控制）
        response = await self.client._chat_completion_raw(
            messages=message,
            **self.chat_params
        )
        return response

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=5, min=4, max=60))
    async def _get_valid_completion(self, message: List[Dict[str, str]], validate_json: bool = False) -> str:
        """Get completion with validation and retry logic for both API and format errors."""
        try:
            response = await self._get_chat_completion_raw(message)
            
            # If JSON validation is required and format validation retry is enabled
            if (validate_json and 
                self.enable_format_validation_retry and 
                self.prompt_config.output_config.get("require_json", False)):
                
                try:
                    # Try to parse the response to validate JSON format
                    parsed_result = self._robust_json_parse(response)
                    # JSON validation successful - no need to print for every item
                except Exception as parse_error:
                    print(f"❌ JSON validation failed: {parse_error}")
                    print(f"📄 Raw response (first 200 chars): {response[:200]}...")
                    
                    # Different strategies based on error type
                    if "Missing required keys" in str(parse_error):
                        print(f"🔑 Missing required keys - retrying with emphasis on required fields...")
                    elif "Parsed data is not a dictionary" in str(parse_error):
                        print(f"📝 Invalid JSON structure - retrying with format emphasis...")
                    elif "Input text is empty" in str(parse_error):
                        print(f"🈳 Empty response - retrying...")
                    else:
                        print(f"🔧 General format issue - retrying...")
                    
                    # Raise an exception to trigger retry
                    raise ValueError(f"JSON format validation failed: {parse_error}")
            
            return response
            
        except Exception as e:
            if "JSON format validation failed" in str(e):
                print(f"🔄 Format validation error, retrying: {str(e)}")
            else:
                print(f"🔄 API error, retrying: {type(e).__name__} - {str(e)}")
            raise
    
    def _robust_json_parse(self, full_text: str) -> Dict[str, Any]:
        """Robustly parse JSON from API response."""
        if not full_text:
            raise ValueError("Input text is empty.")
        
        default_response = self.prompt_config.output_config.get("json_default_values", {})
        required_keys = self.prompt_config.output_config.get("json_key_must_exists", [])
        all_possible_keys = self.prompt_config.output_config.get("json_keys", [])
        
        parsed_dict = None
        
        # Try to find and parse JSON from the text
        json_pattern = re.compile(r'\{.*\}', re.DOTALL)
        match = json_pattern.search(full_text)
        
        if match:
            try:
                parsed_dict = json.loads(match.group(0))
            except json.JSONDecodeError:
                # Try to find JSON within code blocks
                code_block_match = re.search(r'```json\s*(\{.*?\})\s*```', full_text, re.DOTALL)
                if code_block_match:
                    parsed_dict = json.loads(code_block_match.group(1))
                else:
                    parsed_dict = json.loads(full_text)
        
        if not isinstance(parsed_dict, dict):
            raise ValueError("Parsed data is not a dictionary.")
        
        # Validate required keys
        missing_keys = set(required_keys) - set(parsed_dict.keys())
        if missing_keys:
            raise ValueError(f"Missing required keys: {missing_keys}")
        
        # Convert string scores to int if needed
        if parsed_dict.get('score', '') and isinstance(parsed_dict['score'], str) and parsed_dict['score'].isdigit():
            parsed_dict['score'] = int(parsed_dict['score'])
        
        # Build final dictionary with defaults
        result = {}
        for key in all_possible_keys:
            result[key] = parsed_dict.get(key, default_response.get(key))
        
        return result
    
    def _build_message(self, item: Dict[str, Any], input_key: str = "text", prompt_format_key: str = "code_corpus_description_and_sample") -> List[Dict[str, str]]:
        """Build message for API call."""
        prompt_template = self.prompt_config.prompt_template.prompt_text
        
        # Create format kwargs with the primary content and all available item fields
        format_kwargs = {prompt_format_key: item[input_key]}
        
        # Add all item fields for template formatting
        for key, value in item.items():
            format_kwargs[key] = value
        
        try:
            prompt = prompt_template.format_map(format_kwargs)
        except (KeyError, IndexError, ValueError) as e:
            raise ValueError(f"Prompt formatting failed: {e}")
        
        message = []
        if self.prompt_config.prompt_template.get("system_text"):
            message.append({"role": "system", "content": self.prompt_config.prompt_template.system_text})
        
        message.append({"role": "user", "content": prompt})
        return message
    
    async def score_async(self, item: Dict[str, Any], input_key: str = "text", prompt_format_key: str = "code_corpus_description_and_sample") -> Dict[str, Any]:
        """Score a single item asynchronously with format validation and retry."""
        result = copy.deepcopy(item)
        
        try:
            # Build message
            message = self._build_message(item, input_key, prompt_format_key)
            
            # Get API response with validation and retry
            require_json = self.prompt_config.output_config.get("require_json", False)
            response = await self._get_valid_completion(message, validate_json=require_json)
            
            # Parse response (should succeed since we validated in _get_valid_completion)
            if require_json:
                try:
                    parsed = self._robust_json_parse(response)
                    parsed["api_status"] = "success"
                    parsed["api_fail_reason"] = ""
                    parsed["api_return"] = response
                except Exception as parse_error:
                    # This should rarely happen since we validated above, but just in case
                    print(f"⚠️ Unexpected parse error after validation: {parse_error}")
                    parsed = {
                        "api_status": "error",
                        "api_fail_reason": f"Parse error after validation: {parse_error}",
                        "api_return": response
                    }
            else:
                parsed = {
                    "api_status": "success", 
                    "api_fail_reason": "",
                    "api_return": response
                }
            
            # Add default values for missing keys
            for key, default_value in self.prompt_config.output_config.get("json_default_values", {}).items():
                if key not in parsed:
                    parsed[key] = default_value
            
            result.update(parsed)
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Final error scoring item {item.get('id', 'unknown')}: {error_msg}")
            
            # Add context about retry exhaustion
            if "JSON format validation failed" in error_msg:
                error_msg = f"JSON format validation failed after all retries: {error_msg}"
            elif "tenacity" in error_msg.lower() or "retry" in error_msg.lower():
                error_msg = f"API call failed after all retries: {error_msg}"
            
            result.update({
                "api_status": "error",
                "api_fail_reason": error_msg,
                "api_return": getattr(e, 'last_response', ""),
                "score": self.prompt_config.output_config.get("json_default_values", {}).get("score", 0)
            })
            
            # Add all default values for failed items
            for key, default_value in self.prompt_config.output_config.get("json_default_values", {}).items():
                if key not in result:
                    result[key] = default_value
        
        return result
    
    def score(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous score method for compatibility."""
        # For single item, create event loop if not exists
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.score_async(item))


class ConcurrentAPIScorer:
    """Concurrent API scorer for batch processing."""
    
    def __init__(self, api_scorer: APIScorer):
        self.api_scorer = api_scorer
    
    async def score_batch(self, items: List[Dict[str, Any]], input_key: str = "text", prompt_format_key: str = "code_corpus_description_and_sample") -> List[Dict[str, Any]]:
        """Score a batch of items concurrently."""
        tasks = [
            self.api_scorer.score_async(item, input_key, prompt_format_key) 
            for item in items
        ]
        
        return await asyncio.gather(*tasks)

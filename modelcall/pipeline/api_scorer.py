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
from openai import AsyncOpenAI

from ..utils import get_tos_config


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
        
        # Initialize API client
        self.client = self._init_client()
        
        # Request semaphore for rate limiting
        self.request_semaphore = asyncio.Semaphore(max_concurrent_requests)
    
    def _load_config(self, config_path: str) -> EasyDict:
        """Load YAML configuration file."""
        with open(config_path, 'r', encoding='utf-8') as f:
            return EasyDict(yaml.safe_load(f))
    
    def _init_client(self) -> AsyncOpenAI:
        """Initialize OpenAI-compatible API client."""
        base_url = os.environ.get("BASE_URL", "https://api.openai.com/v1")
        api_key = os.environ.get("API_KEY", "")
        
        if not api_key:
            raise ValueError("API_KEY environment variable not set.")
        
        return AsyncOpenAI(base_url=base_url, api_key=api_key)
    
    async def _get_chat_completion_raw(self, message: List[Dict[str, str]]) -> str:
        """Get raw completion from API without retry logic."""
        async with self.request_semaphore:
            response = await self.client.chat.completions.create(
                model=self.model_config.model_name,
                messages=message,
                timeout=self.request_timeout,
                **self.model_config.get("completions_params", {})
            )
            
            response_result = response.choices[0].message.content
            if response_result == "" and response.choices[0].message.reasoning_content:
                response_result = response.choices[0].message.reasoning_content
            
            return response_result

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
                    print(f"✅ Valid JSON response received with keys: {list(parsed_result.keys())}")
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
        format_kwargs = {prompt_format_key: item[input_key]}
        
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

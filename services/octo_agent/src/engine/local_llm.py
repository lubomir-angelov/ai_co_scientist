"""
Local LLM Engine Adapter - communicates with LLM Gateway service
Adapted from octotools engine pattern
"""

import sys
from pathlib import Path
from typing import Any, Union, Optional
import httpx

from .base import EngineLM, CachedEngine


class ChatLocalLLM(EngineLM, CachedEngine):
    """
    Adapter for local LLM via HTTP Gateway
    Communicates with LLM Gateway service for reasoning and planning
    """
    
    system_prompt: str = "You are a helpful, creative, and smart assistant."
    
    def __init__(
        self,
        model_string: str,
        base_url: str = "http://llm-gateway:9000/v1",
        api_key: str = "local-llm",
        use_cache: bool = False,
        is_multimodal: bool = True,
        cache_path: str = ".cache/llm",
        **kwargs
    ):
        """
        Initialize ChatLocalLLM adapter
        
        Args:
            model_string: Model name/identifier
            base_url: LLM Gateway base URL
            api_key: API key for authentication
            use_cache: Enable response caching
            is_multimodal: Support multimodal input
            cache_path: Cache directory path
            **kwargs: Additional arguments
        """
        self.model_string = model_string
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.is_multimodal = is_multimodal
        self.use_cache = use_cache
        self.kwargs = kwargs
        
        if use_cache:
            CachedEngine.__init__(self, cache_path=cache_path)

    def _prepare_headers(self) -> dict:
        """Prepare HTTP headers for requests"""
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
        }

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Generate text using local LLM via gateway
        
        Args:
            prompt: Input prompt
            system_prompt: System message
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional arguments
        
        Returns:
            Generated text
        """
        
        # Check cache if enabled
        cache_key = f"{prompt}:{system_prompt}:{max_tokens}:{temperature}"
        if self.use_cache and hasattr(self, '_check_cache'):
            cached = self._check_cache(cache_key)
            if cached:
                return cached

        # Prepare messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Make request to gateway
        payload = {
            "model": self.model_string,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._prepare_headers(),
                timeout=300.0,
            )
            response.raise_for_status()
            data = response.json()
            
            result = data['choices'][0]['message']['content']
            
            # Cache result if enabled
            if self.use_cache and hasattr(self, '_save_cache'):
                self._save_cache(cache_key, result)
            
            return result
            
        except httpx.HTTPError as e:
            raise RuntimeError(f"LLM Gateway error: {e}")

    def __call__(
        self,
        input_data: Union[str, list],
        **kwargs
    ) -> str:
        """
        Make engine callable for multimodal input
        
        Args:
            input_data: String prompt or list [prompt, image_bytes, ...]
            **kwargs: Additional arguments
        
        Returns:
            Generated text
        """
        
        if isinstance(input_data, str):
            return self.generate(input_data, **kwargs)
        
        elif isinstance(input_data, list) and len(input_data) > 0:
            prompt = input_data[0] if isinstance(input_data[0], str) else str(input_data[0])
            
            # For now, just use text prompt
            # Full multimodal support would require vision endpoint
            return self.generate(prompt, **kwargs)
        
        else:
            raise ValueError(f"Unsupported input type: {type(input_data)}")

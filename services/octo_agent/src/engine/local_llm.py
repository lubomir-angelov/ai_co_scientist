"""
Local LLM Engine Adapter - communicates with the LLM gateway service.
Adapted from the octotools engine pattern.
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel

from engine.base import CachedEngine, EngineLM
from service_errors import LLMEngineError

logger = logging.getLogger(__name__)


class ChatLocalLLM(EngineLM, CachedEngine):
    """
    Adapter for the local LLM via the HTTP gateway.
    Communicates with the LLM gateway service for reasoning and planning.
    """

    system_prompt: str = "You are a helpful, creative, and smart assistant."

    def __init__(
        self,
        model_string: str,
        base_url: str,
        api_key: str,
        is_multimodal: bool,
        timeout_s: float,
        use_cache: bool = False,
        cache_path: str = ".cache/llm",
        **kwargs,
    ):
        """
        Initialize ChatLocalLLM adapter.

        Args:
            model_string: Model identifier as served by the gateway (e.g. the llama.cpp
                --alias); no default and no coercion — this is the id RuntimeConfig.from_env()
                resolved, or the id an agent caller explicitly asked for.
            base_url: LLM gateway base URL.
            api_key: API key for authentication.
            is_multimodal: Support multimodal input.
            timeout_s: Per-request timeout in seconds; no default — callers pass
                RuntimeConfig.from_env().llm_request_timeout_seconds or an explicit value.
            use_cache: Enable response caching.
            cache_path: Cache directory path.
            **kwargs: Additional arguments.
        """
        self.model_string = model_string
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.is_multimodal = is_multimodal
        self.timeout_s = timeout_s
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
        system_prompt: str | None = None,
        max_tokens: int = 4000,
        temperature: float = 0.7,
        response_format: type[BaseModel] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        """
        Generate text (or a validated model instance) using the local LLM via the gateway.

        Args:
            prompt: Input prompt.
            system_prompt: System message.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.
            response_format: When given, the model is asked to answer as this schema
                (structured-output / grammar-constrained), and the return value is a
                validated instance of it instead of a raw string.
            **kwargs: Additional arguments.

        Returns:
            The generated text, or a ``response_format`` instance when one was requested.
        """
        cache_key = f"{prompt}:{system_prompt}:{max_tokens}:{temperature}"
        if response_format is not None:
            cache_key = f"{cache_key}:{response_format.__name__}"
        if self.use_cache and hasattr(self, "_check_cache"):
            cached = self._check_cache(cache_key)
            if cached is not None:
                return response_format.model_validate_json(cached) if response_format else cached

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_string,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_format.__name__,
                    "strict": True,
                    "schema": response_format.model_json_schema(),
                },
            }

        logger.debug("Sending model: %s", self.model_string)

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._prepare_headers(),
                timeout=self.timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMEngineError(
                f"LLM gateway error {exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TransportError as exc:
            raise LLMEngineError(
                f"LLM gateway unreachable at {self.base_url}: {exc}", status_code=None
            ) from exc

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if not content:
            raise LLMEngineError(
                "LLM returned no content (is reasoning mode on?)",
                status_code=response.status_code,
            )

        if self.use_cache and hasattr(self, "_save_cache"):
            self._save_cache(cache_key, content)

        if response_format is not None:
            return response_format.model_validate_json(content)
        return content

    def __call__(self, input_data: str | list, **kwargs) -> str | BaseModel:
        """
        Make engine callable for multimodal input.

        Args:
            input_data: String prompt or list [prompt, image_bytes, ...].
            **kwargs: Additional arguments.

        Returns:
            Generated text, or a ``response_format`` instance when one was requested.
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

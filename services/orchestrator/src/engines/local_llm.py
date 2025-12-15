# services/orchestrator/src/engines/local_llm.py

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatLocalLLM:
    model_string: str
    base_url: str
    api_key: Optional[str] = None
    timeout_s: float = 120.0

    async def chat_completions(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto",
        temperature: float = 0.0,
        max_tokens: int = 512,
        include_reasoning: bool = False,
    ) -> Dict[str, Any]:
        url = self.base_url.rstrip("/") + "/v1/chat/completions"

        payload: Dict[str, Any] = {
            "model": self.model_string,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        if include_reasoning:
            payload["include_reasoning"] = True

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        def _do_request() -> Dict[str, Any]:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8")
                except Exception:
                    pass
                logger.error("LLM HTTPError %s: %s", e.code, err_body[:500])
                raise
            except Exception:
                logger.exception("LLM request failed")
                raise

        return await asyncio.to_thread(_do_request)

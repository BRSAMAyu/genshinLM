from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from llm.provider_base import ProviderRequestError, ProviderUnavailable


class ChatHTTPClient:
    def __init__(
        self,
        api_key_env: str,
        default_base_url: str,
        default_model: str,
        base_url_env: str,
        model_env: str,
        timeout_env: str,
        retry_env: str,
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url = os.getenv(base_url_env, default_base_url)
        self.model = os.getenv(model_env, default_model)
        self.timeout = float(os.getenv(timeout_env, "20"))
        self.retries = int(os.getenv(retry_env, "1"))

    def available(self) -> bool:
        return bool(os.getenv(self.api_key_env))

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 1600) -> tuple[dict[str, Any], dict[str, Any]]:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise ProviderUnavailable(f"{self.api_key_env} is not set; using mock planner fallback.")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "stream": False,
            "max_tokens": max_tokens,
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(
                    self.base_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                data = json.loads(raw)
                content = self._extract_content(data)
                return _extract_json_object(content), dict(data.get("usage", {}))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ProviderRequestError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.35 * (attempt + 1))
        raise ProviderRequestError(f"provider request failed: {last_error}")

    def _extract_content(self, data: dict[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError(f"provider response did not include choices[0].message.content: {data}") from exc


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ProviderRequestError("provider response did not contain a JSON object")
    return json.loads(cleaned[start : end + 1])

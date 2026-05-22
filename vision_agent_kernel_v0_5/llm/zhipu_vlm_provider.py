from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from llm.provider_base import ProviderRequestError, ProviderUnavailable
from llm.vision_output_guard import VisionOutputGuard
from llm.vision_provider import (
    ImageInput,
    ScreenStateResult,
    UIGroundingResult,
    VisionProviderStatus,
    VisionResult,
)


class ZhipuVLMProvider:
    """Cloud VLM provider using Zhipu GLM-4V API (OpenAI-compatible)."""

    name = "zhipu_vlm"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_sec: float | None = None,
        output_guard: VisionOutputGuard | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("ZHIPU_API_KEY", "")
        self.model = model or os.getenv("ZHIPU_VLM_MODEL", "glm-4v-flash")
        default_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self.base_url = base_url or os.getenv("ZHIPU_VLM_BASE_URL", default_url)
        self.timeout_sec = timeout_sec if timeout_sec is not None else float(
            os.getenv("ZHIPU_VLM_TIMEOUT_SEC", "30"),
        )
        self.output_guard = output_guard or VisionOutputGuard()

    def status(self) -> VisionProviderStatus:
        if not self.api_key:
            return VisionProviderStatus(
                self.name, False, self.model, self.base_url, False,
                message="ZHIPU_API_KEY not configured",
            )
        return VisionProviderStatus(
            self.name, True, self.model, self.base_url, True,
            message="configured",
        )

    def describe_image(self, image: ImageInput, prompt: str) -> VisionResult:
        started = time.perf_counter()
        data = self._chat([
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": self._data_url(image)}},
        ])
        latency = (time.perf_counter() - started) * 1000.0
        text = self._extract_content(data)
        return VisionResult(
            self.name, self.model, text, latency,
            usage=dict(data.get("usage", {})), raw=data,
        )

    def ground_ui(self, image: ImageInput, query: str) -> UIGroundingResult:
        prompt = (
            'Return strict JSON only: {"candidates":[{"label":"...",'
            '"bbox_norm":[x,y,w,h],"confidence":0.0,"reason":"..."}]}. '
            f"Find UI element for query: {query}"
        )
        result = self.describe_image(image, prompt)
        candidates: list[dict[str, object]] = []
        try:
            parsed = _extract_json_object(result.text)
            raw_cands = parsed.get("candidates", [])
            if isinstance(raw_cands, list):
                candidates = [c for c in raw_cands if isinstance(c, dict)]
        except Exception:
            candidates = []
        candidates = self.output_guard.validate_grounding_candidates(candidates).accepted
        return UIGroundingResult(self.name, query, candidates, result.latency_ms, result.text)

    def classify_screen(self, image: ImageInput, candidates: list[str]) -> ScreenStateResult:
        prompt = (
            'Return strict JSON only: {"screen_state":"one candidate","confidence":0.0}. '
            f"Candidates: {candidates}"
        )
        result = self.describe_image(image, prompt)
        try:
            parsed = _extract_json_object(result.text)
            state, confidence, _errors = self.output_guard.validate_screen_state(
                str(parsed.get("screen_state", "unknown")),
                candidates,
                float(parsed.get("confidence", 0.0)),
            )
            return ScreenStateResult(self.name, state, confidence, result.latency_ms, result.text)
        except Exception:
            return ScreenStateResult(self.name, "unknown", 0.0, result.latency_ms, result.text)

    def explain_failure_with_image(
        self, summary: dict[str, object], image: ImageInput,
    ) -> dict[str, object]:
        result = self.describe_image(
            image,
            "Return strict JSON with user_friendly_summary, technical_summary, "
            "suggested_next_steps. "
            f"Failure summary: {json.dumps(summary, ensure_ascii=False)}",
        )
        try:
            parsed = _extract_json_object(result.text)
        except Exception:
            parsed = {"technical_summary": result.text, "suggested_next_steps": []}
        parsed.setdefault("provider", self.name)
        parsed.setdefault("latency_ms", result.latency_ms)
        return parsed

    def _chat(self, content: list[dict[str, Any]], max_tokens: int = 1024) -> dict[str, Any]:
        if not self.api_key:
            raise ProviderUnavailable("ZHIPU_API_KEY is not configured")
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.1,
            "stream": False,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderRequestError(f"Zhipu VLM request failed: {exc}") from exc

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError(
                f"Zhipu VLM response missing choices: {data}",
            ) from exc

    @staticmethod
    def _data_url(image: ImageInput) -> str:
        encoded = base64.b64encode(image.data).decode("ascii")
        return f"data:{image.mime_type};base64,{encoded}"


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in text")
    return json.loads(cleaned[start : end + 1])

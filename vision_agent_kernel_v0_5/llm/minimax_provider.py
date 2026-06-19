from __future__ import annotations

import json
import time
from typing import Any

from llm.glm_provider import _system_prompt, _user_prompt
from llm.http_provider import ChatHTTPClient, Transport, _extract_json_object
from llm.provider_base import PlannerProposal
from llm.vision_provider import (
    ImageInput,
    ScreenStateResult,
    UIGroundingResult,
    VisionProviderStatus,
    VisionResult,
)


class MiniMaxProvider:
    """MiniMax M3 — the unified multimodal cloud model.

    One model/endpoint serves both the text planner (:meth:`plan`) and the
    vision calls (:meth:`describe_image` / :meth:`classify_screen` /
    :meth:`ground_ui`). M3 is multimodal, so a screenshot flows straight into the
    same planner conversation when needed. Offline-testable via an injected
    ``transport``.
    """

    name = "minimax"

    def __init__(self, *, transport: Transport | None = None) -> None:
        self._client = ChatHTTPClient(
            api_key_env="MINIMAX_API_KEY",
            # MiniMax OpenAI-compatible endpoint (supports text + vision for M3).
            default_base_url="https://api.minimaxi.com/v1/chat/completions",
            default_model="MiniMax-M3",
            base_url_env="MINIMAX_BASE_URL",
            model_env="MINIMAX_MODEL",
            timeout_env="MINIMAX_TIMEOUT_SEC",
            retry_env="MINIMAX_RETRIES",
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._client.model

    @property
    def base_url(self) -> str:
        return self._client.base_url

    # -- planner -----------------------------------------------------------

    def plan(self, goal: str, skills: list[dict], persona_id: str) -> PlannerProposal:
        task_spec, usage = self._client.chat_json(
            _system_prompt(),
            _user_prompt(goal, skills, persona_id),
            temperature=0.2,
            max_tokens=1600,
        )
        skill_chain = [str(item) for item in task_spec.get("skill_chain", [])]
        return PlannerProposal(self.name, task_spec, skill_chain, ["Real execution requires user confirmation."], usage=usage)

    def explain_failure(self, summary: dict) -> dict:
        payload, usage = self._client.chat_json(
            "Return strict JSON with user_friendly_summary, technical_summary, suggested_next_steps, possible_skill_patch. Do not modify files.",
            json.dumps({"summary": summary}, ensure_ascii=False),
            temperature=0.2,
            max_tokens=1000,
        )
        payload.setdefault("usage", usage)
        return payload

    # -- vision (same M3 model) --------------------------------------------

    def status(self) -> VisionProviderStatus:
        return VisionProviderStatus(
            provider=self.name,
            ok=self._client.available(),
            model=self.model,
            base_url=self.base_url,
            supports_images=True,
            message="ready" if self._client.available() else f"{self._client.api_key_env} not set",
        )

    def describe_image(self, image: ImageInput, prompt: str) -> VisionResult:
        started = time.perf_counter()
        text, usage = self._client.chat_text(
            "You are a game-vision assistant. Describe what is on screen relevant to the request, concisely.",
            prompt,
            max_tokens=800,
            images=[image],
        )
        latency = (time.perf_counter() - started) * 1000.0
        return VisionResult(self.name, self.model, text, latency, usage=dict(usage))

    def classify_screen(self, image: ImageInput, candidates: list[str]) -> ScreenStateResult:
        started = time.perf_counter()
        system = (
            "Return strict JSON only: {\"screen_state\":\"one candidate\","
            "\"confidence\":0.0}. Pick the single best match."
        )
        user = json.dumps({"candidates": candidates}, ensure_ascii=False)
        payload, usage = self._client.chat_json(system, user, temperature=0.1, max_tokens=200, images=[image])
        latency = (time.perf_counter() - started) * 1000.0
        return ScreenStateResult(
            provider=self.name,
            screen_state=str(payload.get("screen_state", "unknown")),
            confidence=float(payload.get("confidence", 0.0)),
            latency_ms=latency,
            raw_text=json.dumps(payload, ensure_ascii=False),
        )

    def ground_ui(self, image: ImageInput, query: str) -> UIGroundingResult:
        started = time.perf_counter()
        system = (
            "Return strict JSON only: {\"candidates\":[{\"label\":\"...\","
            "\"bbox_norm\":[x,y,w,h],\"confidence\":0.0,\"reason\":\"...\"}]}. "
            "bbox_norm is normalized [0,1] (x,y,w,h)."
        )
        user = f"Find the UI element for query: {query}"
        payload, _usage = self._client.chat_json(system, user, temperature=0.1, max_tokens=400, images=[image])
        latency = (time.perf_counter() - started) * 1000.0
        candidates = list(payload.get("candidates", [])) if isinstance(payload, dict) else []
        return UIGroundingResult(
            provider=self.name, query=query, candidates=candidates, latency_ms=latency,
            raw_text=json.dumps(payload, ensure_ascii=False),
        )

    def explain_failure_with_image(self, summary: dict[str, object], image: ImageInput) -> dict[str, object]:
        system = (
            "Return strict JSON with user_friendly_summary, technical_summary, "
            "suggested_next_steps, possible_skill_patch. Use the screenshot as evidence."
        )
        payload, usage = self._client.chat_json(
            system,
            json.dumps({"summary": summary}, ensure_ascii=False),
            temperature=0.2,
            max_tokens=900,
            images=[image],
        )
        payload.setdefault("usage", usage)
        return payload

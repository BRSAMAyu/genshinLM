"""Gemma-family local vision backends.

`gemma4_vision` is treated as a configurable local profile alias. The actual
model id is supplied by the user's endpoint or local Transformers cache.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from llm.local_vlm_provider import OpenAICompatibleLocalVisionProvider, _extract_json_object
from llm.provider_base import ProviderRequestError, ProviderUnavailable
from llm.vision_output_guard import VisionOutputGuard
from llm.vision_provider import (
    ImageInput,
    VisionBackendStatus,
    VisionFact,
    VisionFactBundle,
)


_FACT_PROMPT = (
    "Return strict JSON only with keys: screen_state, uncertainty, facts. "
    "facts must be a list of {fact_id,fact_type,value,confidence,evidence_ref,bbox_norm}. "
    "Allowed fact_type values include screen_state, ocr_text_hint, ui_grounding, "
    "map_marker_hypothesis, dialogue_region, uncertainty. Do not output actions, "
    "clicks, key presses, or physical coordinates."
)


class OpenAICompatibleGemmaVisionBackend:
    name = "gemma_openai_compatible"

    def __init__(
        self,
        base_url: str | None = None,
        model_id: str = "gemma4_vision",
        output_guard: VisionOutputGuard | None = None,
    ) -> None:
        self.provider = OpenAICompatibleLocalVisionProvider(base_url=base_url, model=model_id, output_guard=output_guard)
        self.output_guard = output_guard or VisionOutputGuard()

    def status(self) -> VisionBackendStatus:
        status = self.provider.status()
        return VisionBackendStatus(
            backend=self.name,
            ok=status.ok,
            model_id=status.model,
            endpoint=status.base_url,
            supports_images=status.supports_images,
            latency_ms=status.latency_ms,
            message=status.message,
        )

    def extract_facts(self, image: ImageInput, prompt: str = "") -> VisionFactBundle:
        started = time.perf_counter()
        result = self.provider.describe_image(image, prompt or _FACT_PROMPT)
        facts, screen_state, uncertainty = _parse_fact_bundle(result.text, self.output_guard)
        return VisionFactBundle(
            provider=self.name,
            model=result.model,
            screen_state=screen_state,
            facts=tuple(facts),
            uncertainty=uncertainty,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            raw_text=result.text,
        )


@dataclass(slots=True)
class TransformersGemmaVisionBackend:
    """Optional local Transformers backend.

    Dependencies and model weights are intentionally lazy-loaded so this class
    can be imported on machines that do not have Transformers installed.
    """

    model_id: str = "gemma4_vision"
    device: str = "cpu"
    dtype: str = "auto"
    output_guard: VisionOutputGuard | None = None
    name: str = "gemma_transformers"

    def status(self) -> VisionBackendStatus:
        try:
            import importlib.util
            has_transformers = importlib.util.find_spec("transformers") is not None
            has_torch = importlib.util.find_spec("torch") is not None
        except Exception as exc:
            return VisionBackendStatus(self.name, False, self.model_id, supports_images=False, message=str(exc))
        if not has_transformers or not has_torch:
            return VisionBackendStatus(
                self.name,
                False,
                self.model_id,
                supports_images=False,
                message="transformers/torch unavailable; use OpenAI-compatible backend or deterministic fallback",
            )
        return VisionBackendStatus(self.name, True, self.model_id, supports_images=True, message="dependencies_available")

    def extract_facts(self, image: ImageInput, prompt: str = "") -> VisionFactBundle:
        status = self.status()
        if not status.ok:
            raise ProviderUnavailable(status.message)
        raise ProviderRequestError(
            "TransformersGemmaVisionBackend is an optional integration point; "
            "configure a concrete processor/model runner before live inference."
        )


def _parse_fact_bundle(text: str, guard: VisionOutputGuard) -> tuple[list[VisionFact], str, float]:
    try:
        parsed = _extract_json_object(text)
    except Exception:
        parsed = {"screen_state": "unknown", "uncertainty": 1.0, "facts": []}
    screen_state = str(parsed.get("screen_state", "unknown"))
    uncertainty = _float(parsed.get("uncertainty", 1.0), 1.0)
    facts: list[VisionFact] = []
    for idx, item in enumerate(parsed.get("facts", []) if isinstance(parsed.get("facts", []), list) else []):
        if not isinstance(item, dict):
            continue
        fact_type = str(item.get("fact_type", ""))
        value: Any = item.get("value", "")
        confidence = max(0.0, min(1.0, _float(item.get("confidence", 0.0), 0.0)))
        bbox = _bbox_tuple(item.get("bbox_norm"))
        candidate = {
            "label": json.dumps(value, ensure_ascii=False)[:80],
            "bbox_norm": list(bbox) if bbox else [0.0, 0.0, 1.0, 1.0],
            "confidence": confidence,
            "reason": fact_type,
        }
        if fact_type == "ui_grounding" and not guard.validate_candidate(candidate).ok:
            continue
        if confidence < guard.min_confidence and fact_type != "uncertainty":
            continue
        facts.append(VisionFact(
            fact_id=str(item.get("fact_id") or f"vf_{idx}"),
            fact_type=fact_type,
            value=value,
            confidence=confidence,
            evidence_ref=str(item.get("evidence_ref", "")),
            bbox_norm=bbox,
            source="gemma",
        ))
    return facts, screen_state, uncertainty


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bbox_tuple(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, w, h = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1 or y + h > 1:
        return None
    return (x, y, w, h)

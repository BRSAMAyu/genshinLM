from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from benchmarks.local_vlm_bench import LocalVlmBenchResult
from llm.vision_provider import VisionProviderStatus


ModelRoute = Literal["deterministic", "local_vlm", "cloud_llm", "ask_user"]


@dataclass(frozen=True, slots=True)
class ModelRouteDecision:
    route: ModelRoute
    reason: str
    requires_image: bool = False
    allow_cloud: bool = False


@dataclass(frozen=True, slots=True)
class ModelRoutePolicy:
    local_max_latency_ms: float = 1800.0
    local_min_grounding_success: float = 0.75
    simple_complexity_threshold: float = 0.35
    local_complexity_threshold: float = 0.75
    cloud_allowed: bool = True

    def decide(
        self,
        *,
        task_type: str,
        complexity_score: float,
        local_status: VisionProviderStatus | None = None,
        bench_result: LocalVlmBenchResult | None = None,
        deterministic_available: bool = False,
        image_required: bool = False,
        safety_risk: str = "low",
    ) -> ModelRouteDecision:
        if deterministic_available and complexity_score <= self.simple_complexity_threshold:
            return ModelRouteDecision("deterministic", "low_complexity_deterministic_path", image_required, False)
        if safety_risk == "human_confirm":
            return ModelRouteDecision("ask_user", "human_confirmation_risk", image_required, False)
        if self._local_ready(local_status, bench_result) and complexity_score <= self.local_complexity_threshold:
            return ModelRouteDecision("local_vlm", "local_vlm_within_latency_and_quality_budget", image_required, False)
        if self.cloud_allowed and task_type in {"failure_explanation", "long_horizon_planning", "repair", "ambiguous_visual_reasoning"}:
            return ModelRouteDecision("cloud_llm", "complex_task_or_local_quality_insufficient", image_required, True)
        return ModelRouteDecision("ask_user", "no_model_route_meets_policy", image_required, False)

    def _local_ready(self, status: VisionProviderStatus | None, bench_result: LocalVlmBenchResult | None) -> bool:
        if status is None or not status.ok or not status.supports_images:
            return False
        if status.latency_ms > self.local_max_latency_ms:
            return False
        if bench_result is not None and bench_result.ui_grounding_success_rate < self.local_min_grounding_success:
            return False
        return True

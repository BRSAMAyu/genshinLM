from __future__ import annotations

import time
from dataclasses import dataclass

from llm.vision_provider import ImageInput, VisionLLMProvider


@dataclass(frozen=True, slots=True)
class LocalVlmBenchResult:
    provider: str
    model: str
    latency_p50_ms: float
    latency_p95_ms: float
    json_valid_rate: float
    screen_state_accuracy: float
    ui_grounding_success_rate: float
    failure_explanation_success_rate: float
    ok: bool = True
    message: str = ""


class LocalVlmBench:
    """Tiny deterministic bench harness for local VLM provider comparisons."""

    def __init__(self, provider: VisionLLMProvider) -> None:
        self.provider = provider

    def run_smoke(self) -> LocalVlmBenchResult:
        image = ImageInput(_one_pixel_png(), "image/png", frame_id=1, roi_id="smoke")
        latencies: list[float] = []
        json_ok = 0
        screen_ok = 0
        ui_ok = 0
        failure_ok = 0

        started = time.perf_counter()
        screen = self.provider.classify_screen(image, ["menu", "combat", "unknown"])
        latencies.append(screen.latency_ms)
        screen_ok += 1 if screen.screen_state in {"menu", "combat", "unknown"} else 0
        json_ok += 1 if screen.raw_text else 0

        ui = self.provider.ground_ui(image, "confirm button")
        latencies.append(ui.latency_ms)
        ui_ok += 1 if isinstance(ui.candidates, list) else 0
        json_ok += 1 if ui.raw_text else 0

        failure = self.provider.explain_failure_with_image({"failure_code": "ANCHOR_CLICK_NO_EFFECT"}, image)
        latencies.append(float(failure.get("latency_ms", (time.perf_counter() - started) * 1000.0)))
        failure_ok += 1 if "technical_summary" in failure or "user_friendly_summary" in failure else 0
        json_ok += 1 if failure else 0

        status = self.provider.status()
        ordered = sorted(latencies)
        p50 = ordered[len(ordered) // 2]
        p95 = ordered[-1]
        return LocalVlmBenchResult(
            provider=status.provider,
            model=status.model,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            json_valid_rate=json_ok / 3.0,
            screen_state_accuracy=screen_ok / 1.0,
            ui_grounding_success_rate=ui_ok / 1.0,
            failure_explanation_success_rate=failure_ok / 1.0,
            ok=status.ok,
            message=status.message,
        )

    def run_optional_smoke(self) -> LocalVlmBenchResult:
        """Run a smoke bench without making local VLM availability mandatory."""
        status = self.provider.status()
        if not status.ok:
            return LocalVlmBenchResult(
                provider=status.provider,
                model=status.model,
                ok=False,
                latency_p50_ms=status.latency_ms,
                latency_p95_ms=status.latency_ms,
                json_valid_rate=0.0,
                screen_state_accuracy=0.0,
                ui_grounding_success_rate=0.0,
                failure_explanation_success_rate=0.0,
                message=f"local_vlm_unavailable_requires_human_confirm:{status.message}",
            )
        try:
            return self.run_smoke()
        except Exception as exc:
            return LocalVlmBenchResult(
                provider=status.provider,
                model=status.model,
                ok=False,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                json_valid_rate=0.0,
                screen_state_accuracy=0.0,
                ui_grounding_success_rate=0.0,
                failure_explanation_success_rate=0.0,
                message=f"local_vlm_smoke_failed_requires_human_confirm:{exc}",
            )


def _one_pixel_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01"
        b"\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
    )

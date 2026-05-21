from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DriftSignal:
    signal_id: str
    detector_type: str
    score: float
    description: str


@dataclass(frozen=True, slots=True)
class DriftReport:
    drifted: bool
    signals: list[DriftSignal]
    affected_skills: list[str]
    recommendation: str


class DriftDetector:
    """Detect environment version changes that invalidate historical reliability.

    Checks for layout shifts, OCR anchor shifts, template match drops,
    and detector confidence drops (Section 7.5).
    """

    def __init__(
        self,
        layout_shift_threshold: float = 0.3,
        ocr_shift_threshold: float = 0.25,
        template_drop_threshold: float = 0.3,
        confidence_drop_threshold: float = 0.2,
    ) -> None:
        self.layout_shift_threshold = layout_shift_threshold
        self.ocr_shift_threshold = ocr_shift_threshold
        self.template_drop_threshold = template_drop_threshold
        self.confidence_drop_threshold = confidence_drop_threshold
        self._baselines: dict[str, dict[str, float]] = {}

    def set_baseline(self, component_id: str, metrics: dict[str, float]) -> None:
        self._baselines[component_id] = dict(metrics)

    def check(
        self,
        component_id: str,
        current_metrics: dict[str, float],
        affected_skills: list[str] | None = None,
    ) -> DriftReport:
        baseline = self._baselines.get(component_id)
        if baseline is None:
            return DriftReport(False, [], [], "no_baseline")
        signals: list[DriftSignal] = []
        for metric_name, current_value in current_metrics.items():
            baseline_value = baseline.get(metric_name)
            if baseline_value is None:
                continue
            delta = abs(current_value - baseline_value)
            threshold = self._pick_threshold(metric_name)
            if delta > threshold:
                signals.append(DriftSignal(
                    signal_id=f"{component_id}:{metric_name}",
                    detector_type=self._classify_metric(metric_name),
                    score=delta,
                    description=f"{metric_name}: baseline={baseline_value:.3f} current={current_value:.3f} delta={delta:.3f}",
                ))
        drifted = len(signals) > 0
        skills = affected_skills or []
        recommendation = "invalidate_and_bootstrap" if drifted else "stable"
        return DriftReport(drifted, signals, skills, recommendation)

    def _pick_threshold(self, metric_name: str) -> float:
        name = metric_name.lower()
        if "layout" in name or "position" in name:
            return self.layout_shift_threshold
        if "ocr" in name or "anchor" in name:
            return self.ocr_shift_threshold
        if "template" in name or "match" in name:
            return self.template_drop_threshold
        if "confidence" in name or "detection" in name:
            return self.confidence_drop_threshold
        return 0.3

    @staticmethod
    def _classify_metric(metric_name: str) -> str:
        name = metric_name.lower()
        if "layout" in name or "position" in name:
            return "layout_shift"
        if "ocr" in name or "anchor" in name:
            return "ocr_anchor_shift"
        if "template" in name or "match" in name:
            return "template_match_drop"
        if "confidence" in name or "detection" in name:
            return "detector_confidence_drop"
        return "unknown"

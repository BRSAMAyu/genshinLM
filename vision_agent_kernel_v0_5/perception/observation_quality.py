from __future__ import annotations

import time
from dataclasses import dataclass, field

from perception.observation_graph import ObservationGraph


@dataclass(frozen=True, slots=True)
class ObservationQualityReport:
    graph_id: str
    ok: bool
    issues: list[str] = field(default_factory=list)
    stale_age_ms: float = 0.0
    evidence_coverage: float = 0.0


class ObservationQualityChecker:
    def __init__(self, max_stale_ms: float = 500.0, min_screen_confidence: float = 0.35) -> None:
        self.max_stale_ms = max_stale_ms
        self.min_screen_confidence = min_screen_confidence

    def check(self, graph: ObservationGraph, now: float | None = None) -> ObservationQualityReport:
        current = now if now is not None else time.time()
        age_ms = max(0.0, (current - graph.created_at) * 1000.0)
        issues: list[str] = []
        if age_ms > self.max_stale_ms:
            issues.append("stale_frame")
        screen_nodes = graph.by_kind("screen_state")
        if not screen_nodes:
            issues.append("missing_screen_state")
        elif max(node.confidence for node in screen_nodes) < self.min_screen_confidence:
            issues.append("low_screen_state_confidence")
        if not graph.by_kind("ui_element") and not graph.by_kind("target_track"):
            issues.append("low_evidence_coverage")
        coverage_sources = sum(1 for kind in ("ui_element", "target_track", "danger_signal", "navigation_signal") if graph.by_kind(kind))
        coverage = coverage_sources / 4.0
        return ObservationQualityReport(graph.graph_id, ok=not issues, issues=issues, stale_age_ms=age_ms, evidence_coverage=coverage)

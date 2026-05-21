from __future__ import annotations

from execution.verifier_base import VerifierContext, VerifierResult, ensure_context
from perception.observation_graph import ObservationGraph


def _graph(ctx: VerifierContext) -> ObservationGraph | None:
    value = ctx.metadata.get("observation_graph")
    return value if isinstance(value, ObservationGraph) else None


class ObservationGraphUIVerifier:
    verifier_id = "observation_graph_ui"

    def __init__(self, expected_screen_state: str | None = None, required_anchor: str | None = None) -> None:
        self.expected_screen_state = expected_screen_state
        self.required_anchor = required_anchor

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        graph = _graph(ctx)
        if graph is None:
            return VerifierResult(False, self.verifier_id, 0.0, "observation_graph missing")
        screen_ok = self.expected_screen_state is None or graph.screen_state() == self.expected_screen_state
        anchor_ok = True
        if self.required_anchor is not None:
            anchor_ok = any(
                node.payload.get("anchor_id") == self.required_anchor
                or node.payload.get("id") == self.required_anchor
                or node.node_id == self.required_anchor
                for node in graph.by_kind("ui_element")
            )
        ok = screen_ok and anchor_ok
        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=0.9 if ok else 0.35,
            reason="ui evidence accepted" if ok else "ui evidence missing",
            evidence=graph.evidence_summary(),
            frame_id=graph.frame_id,
            roi_ids=[node.roi_id for node in graph.by_kind("ui_element")],
            detection_confidence=0.9 if ok else 0.35,
        )


class NavigationProgressVerifier:
    verifier_id = "navigation_progress"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        graph = _graph(ctx)
        signals = graph.by_kind("navigation_signal") if graph else []
        progress = max((float(node.payload.get("progress", 0.0)) for node in signals), default=0.0)
        ok = progress > 0.0 or bool(ctx.state.get("arrived"))
        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=0.85 if ok else 0.25,
            reason="navigation progressed" if ok else "navigation did not progress",
            evidence={"progress": progress, "observation_graph": graph.evidence_summary() if graph else None},
            frame_id=graph.frame_id if graph else None,
            roi_ids=[node.roi_id for node in signals],
            detection_confidence=0.85 if ok else 0.25,
        )


class CombatDangerClearedVerifier:
    verifier_id = "combat_danger_cleared"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        graph = _graph(ctx)
        danger_nodes = graph.by_kind("danger_signal") if graph else []
        max_danger = max((float(node.payload.get("danger_score", node.confidence)) for node in danger_nodes), default=0.0)
        ok = max_danger < 0.3
        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=0.9 if ok else 0.4,
            reason="danger cleared" if ok else "danger still present",
            evidence={"max_danger": max_danger, "observation_graph": graph.evidence_summary() if graph else None},
            frame_id=graph.frame_id if graph else None,
            roi_ids=[node.roi_id for node in danger_nodes],
            detection_confidence=0.9 if ok else 0.4,
        )

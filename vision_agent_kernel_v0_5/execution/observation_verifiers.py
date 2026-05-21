from __future__ import annotations

from execution.verifier_base import SignalCorroboration, VerifierContext, VerifierResult, ensure_context
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
            return VerifierResult(
                False, self.verifier_id, 0.0, "observation_graph missing",
                re_verify_recommended=True,
            )
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
        alt_signals: list[SignalCorroboration] = []
        if not ok:
            ocr_nodes = graph.by_kind("ocr_block")
            if ocr_nodes:
                best_ocr = max(ocr_nodes, key=lambda n: n.confidence)
                alt_signals.append(SignalCorroboration(
                    signal_id=best_ocr.node_id, source="ocr",
                    supports_ok=False, confidence=best_ocr.confidence,
                    description="ocr_text_found_but_screen_mismatch",
                ))
        fn_likelihood = 0.0
        re_verify = False
        if not ok and alt_signals:
            max_alt = max((s.confidence for s in alt_signals), default=0.0)
            if max_alt > 0.7:
                fn_likelihood = max_alt * 0.5
                re_verify = True
        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=0.9 if ok else 0.35,
            reason="ui evidence accepted" if ok else "ui evidence missing",
            evidence=graph.evidence_summary(),
            frame_id=graph.frame_id,
            roi_ids=[node.roi_id for node in graph.by_kind("ui_element")],
            detection_confidence=0.9 if ok else 0.35,
            alternative_signals=alt_signals,
            false_negative_likelihood=fn_likelihood,
            re_verify_recommended=re_verify,
        )


class NavigationProgressVerifier:
    verifier_id = "navigation_progress"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        graph = _graph(ctx)
        signals = graph.by_kind("navigation_signal") if graph else []
        progress = max((float(node.payload.get("progress", 0.0)) for node in signals), default=0.0)
        arrived = bool(ctx.state.get("arrived"))
        ok = progress > 0.0 or arrived
        alt_signals: list[SignalCorroboration] = []
        if not ok and graph:
            ui_state = graph.screen_state()
            if ui_state and ui_state != "unknown":
                alt_signals.append(SignalCorroboration(
                    signal_id="screen_state", source="screen_classifier",
                    supports_ok=False, confidence=0.6,
                    description="screen_state_present_but_no_navigation_signal",
                ))
        fn_likelihood = 0.3 if (not ok and arrived) else 0.0
        re_verify = not ok and bool(signals)
        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=0.85 if ok else 0.25,
            reason="navigation progressed" if ok else "navigation did not progress",
            evidence={"progress": progress, "observation_graph": graph.evidence_summary() if graph else None},
            frame_id=graph.frame_id if graph else None,
            roi_ids=[node.roi_id for node in signals],
            detection_confidence=0.85 if ok else 0.25,
            alternative_signals=alt_signals,
            false_negative_likelihood=fn_likelihood,
            re_verify_recommended=re_verify,
        )


class CombatDangerClearedVerifier:
    verifier_id = "combat_danger_cleared"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        graph = _graph(ctx)
        danger_nodes = graph.by_kind("danger_signal") if graph else []
        max_danger = max((float(node.payload.get("danger_score", node.confidence)) for node in danger_nodes), default=0.0)
        ok = max_danger < 0.3
        alt_signals: list[SignalCorroboration] = []
        if not ok and graph:
            if graph.screen_state() not in ("combat", "turn_based_combat", "unknown"):
                alt_signals.append(SignalCorroboration(
                    signal_id="screen_state", source="screen_classifier",
                    supports_ok=True, confidence=0.7,
                    description="screen_no_longer_combat_suggests_danger_cleared",
                ))
        fn_likelihood = 0.4 if (not ok and alt_signals) else 0.0
        re_verify = not ok and len(danger_nodes) <= 1
        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=0.9 if ok else 0.4,
            reason="danger cleared" if ok else "danger still present",
            evidence={"max_danger": max_danger, "observation_graph": graph.evidence_summary() if graph else None},
            frame_id=graph.frame_id if graph else None,
            roi_ids=[node.roi_id for node in danger_nodes],
            detection_confidence=0.9 if ok else 0.4,
            alternative_signals=alt_signals,
            false_negative_likelihood=fn_likelihood,
            re_verify_recommended=re_verify,
        )

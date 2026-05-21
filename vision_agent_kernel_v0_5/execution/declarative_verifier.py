from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from execution.verifier_base import VerifierContext
from perception.observation_graph import ObservationGraph, ObservationNode
from runtime.claim_runtime import ObservationClaim, StateDeltaClaim, _clamp
from runtime.verifier_compiler import VerifierBundle, VerifierStep


@dataclass(frozen=True, slots=True)
class DeclarativeStepResult:
    step: VerifierStep
    ok: bool
    source_family: str
    signal_quality: float
    graph_node_refs: list[str]
    reason: str


class DeclarativeVerifierEngine:
    """Execute VerifierBundle declarations against ObservationGraph evidence."""

    def verify_bundle(
        self,
        *,
        claim: StateDeltaClaim,
        bundle: VerifierBundle,
        context: VerifierContext,
    ) -> list[ObservationClaim]:
        observations: list[ObservationClaim] = []
        for stage, steps in (("primary", bundle.primary), ("secondary", bundle.secondary), ("delayed_audit", bundle.delayed_audit)):
            for index, step in enumerate(steps):
                result = self.verify_step(step, context, claim=claim)
                observations.append(self._to_observation_claim(claim, result, stage, index))
        return observations

    def verify_step(
        self,
        step: VerifierStep,
        context: VerifierContext,
        *,
        claim: StateDeltaClaim | None = None,
    ) -> DeclarativeStepResult:
        graph = _graph_from_context(context)
        if step.type == "composite":
            return self._verify_composite(step, context, claim=claim)
        if graph is None:
            return DeclarativeStepResult(step, False, _family_for_step(step), 0.0, [], "missing_observation_graph")

        if step.type == "screen_state_match":
            expected = step.state or str((claim.claimed_delta if claim else {}).get("screen_state", ""))
            actual = graph.screen_state()
            return _step_result(step, actual == expected, "screen_state", 0.9 if actual == expected else 0.2, [f"screen_state:{actual}"], f"{actual}=={expected}")
        if step.type == "screen_state_transition":
            expected = step.to_state or str((claim.claimed_delta if claim else {}).get("screen_state", ""))
            actual = graph.screen_state()
            previous = str(context.metadata.get("previous_screen_state", step.from_state or ""))
            from_ok = not step.from_state or previous == step.from_state
            ok = bool(expected) and actual == expected and from_ok
            refs = [node.node_id for node in graph.by_kind("screen_state")]
            return _step_result(step, ok, "screen_state", _best_conf(graph.by_kind("screen_state")) if ok else 0.2, refs, f"{previous}->{actual}, expected {step.from_state}->{expected}")
        if step.type == "screen_state_stable":
            expected = step.state
            actual = graph.screen_state()
            stable_frames = int(context.metadata.get("stable_frames", step.frames or 1))
            ok = (not expected or actual == expected) and stable_frames >= max(1, step.frames)
            refs = [node.node_id for node in graph.by_kind("screen_state")]
            return _step_result(step, ok, "screen_state", _best_conf(graph.by_kind("screen_state")) if ok else 0.2, refs, f"stable_frames={stable_frames}")
        if step.type in {"anchor_exists", "element_appearance"}:
            nodes = _matching_anchor_nodes(graph, step.anchor)
            return _step_result(step, bool(nodes), _family_for_step(step), _best_conf(nodes), [n.node_id for n in nodes], "anchor_present" if nodes else "anchor_missing")
        if step.type in {"anchor_not_exists", "element_disappearance"}:
            nodes = _matching_anchor_nodes(graph, step.anchor)
            return _step_result(step, not nodes, _family_for_step(step), 0.9 if not nodes else 0.2, [n.node_id for n in nodes], "anchor_absent" if not nodes else "anchor_still_present")
        if step.type in {"text_match", "regex_match"}:
            nodes = _text_nodes(graph, roi=step.roi)
            matched = _match_text(nodes, step)
            return _step_result(step, bool(matched), "toast" if "toast" in step.roi else "ocr_text", _best_conf(matched), [n.node_id for n in matched], "text_matched" if matched else "text_missing")
        if step.type == "numeric_delta":
            ok, quality, reason, refs = _numeric_delta(context, step, claim, graph)
            return _step_result(step, ok, "inventory_delta", quality, refs, reason)
        if step.type == "progress_threshold":
            nodes = graph.by_kind("navigation_signal")
            best = max((_float(n.payload.get("progress", 0.0)) for n in nodes), default=0.0)
            ok = best >= step.threshold
            return _step_result(step, ok, "navigation_signal", _clamp(best), [n.node_id for n in nodes], f"progress={best:.3f}")
        if step.type == "danger_score_below":
            nodes = graph.by_kind("danger_signal")
            best = min((_float(n.payload.get("danger_score", 1.0)) for n in nodes), default=1.0)
            ok = best <= step.threshold
            return _step_result(step, ok, "combat_danger", _clamp(1.0 - best), [n.node_id for n in nodes], f"danger={best:.3f}")
        if step.type == "color_region_change":
            current, refs = _graph_or_state_float(graph, "color_delta", "color_region_change", context)
            ok = current >= step.threshold
            return _step_result(step, ok, "color", _clamp(current), refs, f"color_delta={current:.3f}")
        if step.type == "temporal_pattern_match":
            current, refs = _graph_or_state_float(graph, "temporal_pattern_match", "temporal_pattern_match", context)
            ok = current >= max(step.threshold, 0.5)
            return _step_result(step, ok, "temporal_pattern", _clamp(current), refs, f"temporal_pattern={current:.3f}")

        return DeclarativeStepResult(step, False, "unknown_verifier_step", 0.0, [], f"unsupported_step:{step.type}")

    def _verify_composite(
        self,
        step: VerifierStep,
        context: VerifierContext,
        *,
        claim: StateDeltaClaim | None = None,
    ) -> DeclarativeStepResult:
        all_results = [self.verify_step(child, context, claim=claim) for child in step.all_of]
        any_results = [self.verify_step(child, context, claim=claim) for child in step.any_of]
        all_ok = all(result.ok for result in all_results) if all_results else True
        any_ok = any(result.ok for result in any_results) if any_results else True
        ok = all_ok and any_ok
        refs = [ref for result in [*all_results, *any_results] for ref in result.graph_node_refs]
        quality_values = [result.signal_quality for result in [*all_results, *any_results]]
        quality = min(quality_values) if ok and quality_values else 0.0
        return DeclarativeStepResult(step, ok, "composite", quality, refs, "composite_ok" if ok else "composite_failed")

    @staticmethod
    def _to_observation_claim(
        claim: StateDeltaClaim,
        result: DeclarativeStepResult,
        stage: str,
        index: int,
    ) -> ObservationClaim:
        return ObservationClaim(
            observation_id=f"obs:{claim.claim_id}:{stage}:{index}:{uuid.uuid4()}",
            claim_id=claim.claim_id,
            source_family=result.source_family,
            polarity="support" if result.ok else "refute",
            signal_quality=result.signal_quality,
            graph_node_refs=result.graph_node_refs,
            verifier_id=f"declarative:{result.step.type}",
            confidence=result.signal_quality,
            metadata={
                "stage": stage,
                "step_type": str(result.step.type),
                "reason": result.reason,
                "freshness": 1.0,
            },
        )


def _graph_from_context(context: VerifierContext) -> ObservationGraph | None:
    graph = context.metadata.get("observation_graph")
    return graph if isinstance(graph, ObservationGraph) else None


def _step_result(
    step: VerifierStep,
    ok: bool,
    family: str,
    quality: float,
    refs: list[str],
    reason: str,
) -> DeclarativeStepResult:
    return DeclarativeStepResult(step, ok, family, _clamp(quality), refs, reason)


def _best_conf(nodes: Iterable[ObservationNode]) -> float:
    return _clamp(max((node.confidence for node in nodes), default=0.0))


def _family_for_step(step: VerifierStep) -> str:
    if step.type in {"anchor_exists", "anchor_not_exists"}:
        return "anchor"
    if step.type in {"element_appearance", "element_disappearance"}:
        return "element"
    return str(step.type)


def _matching_anchor_nodes(graph: ObservationGraph, anchor: str) -> list[ObservationNode]:
    if not anchor:
        return []
    result: list[ObservationNode] = []
    for node in graph.by_kind("ui_element"):
        text = str(node.payload.get("text", ""))
        anchor_id = str(node.payload.get("anchor_id", node.payload.get("metadata", {}).get("anchor_id", "")))
        icon_id = str(node.payload.get("icon_id", ""))
        detector_class = str(node.payload.get("detector_class", ""))
        if anchor in {node.node_id, anchor_id, icon_id, detector_class} or (text and anchor.lower() in text.lower()):
            result.append(node)
    return result


def _text_nodes(graph: ObservationGraph, roi: str = "") -> list[ObservationNode]:
    nodes = [*graph.by_kind("ocr_block"), *graph.by_kind("ui_element")]
    if not roi:
        return nodes
    return [node for node in nodes if node.roi_id == roi or roi in node.roi_id or str(node.payload.get("roi", "")) == roi]


def _match_text(nodes: list[ObservationNode], step: VerifierStep) -> list[ObservationNode]:
    needles = [step.contains] if step.contains else list(step.contains_any)
    needles = [needle.lower() for needle in needles if needle]
    if step.type == "regex_match" and step.contains:
        pattern = re.compile(step.contains)
        return [node for node in nodes if pattern.search(str(node.payload.get("text", "")))]
    if not needles:
        return [node for node in nodes if str(node.payload.get("text", ""))]
    matched: list[ObservationNode] = []
    for node in nodes:
        text = str(node.payload.get("text", "")).lower()
        if any(needle in text for needle in needles):
            matched.append(node)
    return matched


def _numeric_delta(
    context: VerifierContext,
    step: VerifierStep,
    claim: StateDeltaClaim | None,
    graph: ObservationGraph | None,
) -> tuple[bool, float, str, list[str]]:
    observed, refs = _graph_or_state_dict(graph, "observed_delta", "numeric_delta", context)
    expected_item = step.item or str((claim.claimed_delta if claim else {}).get("item", ""))
    expected_delta = step.expected_delta or (claim.claimed_delta if claim else {}).get("delta", 0)
    if isinstance(observed, dict):
        if "item" in observed and "delta" in observed:
            ok = (not expected_item or observed.get("item") == expected_item) and _float(observed.get("delta")) == _float(expected_delta)
            return ok, 0.95 if ok else 0.2, f"observed_delta={observed}", refs
        if expected_item and expected_item in observed:
            ok = _float(observed.get(expected_item)) == _float(expected_delta)
            return ok, 0.95 if ok else 0.2, f"observed_item_delta={observed.get(expected_item)}", refs
    return False, 0.0, "numeric_delta_missing", []


def _graph_or_state_float(
    graph: ObservationGraph | None,
    key: str,
    extension_key: str,
    context: VerifierContext,
) -> tuple[float, list[str]]:
    if graph is not None:
        for node in graph.by_kind("capsule_extension"):
            if node.payload.get("key") == extension_key:
                return _float(node.payload.get("value", 0.0)), [node.node_id]
    return _float(context.state.get(key, context.metadata.get(key, 0.0))), []


def _graph_or_state_dict(
    graph: ObservationGraph | None,
    key: str,
    extension_key: str,
    context: VerifierContext,
) -> tuple[Any, list[str]]:
    if graph is not None:
        for node in graph.by_kind("capsule_extension"):
            if node.payload.get("key") == extension_key:
                return node.payload.get("value", {}), [node.node_id]
    return context.state.get(key, context.metadata.get(key, {})), []


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

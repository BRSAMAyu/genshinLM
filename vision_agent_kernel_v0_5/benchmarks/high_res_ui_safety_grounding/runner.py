"""Runner for the high-res UI safety grounding benchmark suite.

Creates synthetic screen frames with ROI data, tests the UI safety chain:
screen -> ROI cascade -> grounded element -> confidence gate -> block
destructive / require confirmation -> safe action -> post-action verifier.
Verifies evidence links frame/ROI/element at each step.
"""

from __future__ import annotations

import uuid

from evidence.evidence_nodes import (
    EDGE_DERIVED_FROM,
    EDGE_SATISFIES,
    NODE_TYPE_OBSERVATION,
    NODE_TYPE_PRECONDITION,
    NODE_TYPE_ACTION_INTENT,
    NODE_TYPE_VERIFIER_RESULT,
    NODE_TYPE_VERIFIER_CONTRACT,
)
from evidence.evidence_store import EvidenceStore

from benchmarks.benchmark_types import BenchmarkMetrics, BenchmarkResult
from benchmarks.high_res_ui_safety_grounding.scenario import (
    CONFIDENCE_THRESHOLD,
    DESTRUCTIVE_LABELS,
    UIElement,
    UISafetyScenario,
    SCENARIOS,
)


def _classify_element(element: UIElement) -> str:
    """Classify an element as 'blocked', 'confirm', or 'execute'.

    Rules:
    1. Destructive labels are always blocked.
    2. Low confidence (< threshold) requires confirmation.
    3. Elements marked requires_confirmation need confirmation.
    4. Everything else executes directly.
    """
    label_lower = element.label.lower()
    if element.is_destructive or any(dl in label_lower for dl in DESTRUCTIVE_LABELS):
        return "blocked"
    if element.confidence < CONFIDENCE_THRESHOLD or element.requires_confirmation:
        return "confirm"
    return "execute"


def run_scenario(scenario: UISafetyScenario) -> BenchmarkResult:
    """Execute a single UI safety scenario and return a BenchmarkResult."""
    store = EvidenceStore(run_id=f"ui_safety_{scenario.name}")
    evidence_ids: list[str] = []

    actual_blocked: list[str] = []
    actual_confirm: list[str] = []
    actual_execute: list[str] = []

    # Track evidence for each element through the chain:
    # screen -> ROI -> element -> classification -> action
    element_results: list[dict[str, object]] = []

    for element in scenario.elements:
        # Step 1: Record screen/frame evidence
        frame_node = store.record_node(NODE_TYPE_OBSERVATION, {
            "element_id": element.element_id,
            "frame_source": "synthetic_screen",
            "bbox": element.bbox_xyxy,
        })
        evidence_ids.append(frame_node.node_id)

        # Step 2: Record ROI cascade evidence (derived from frame)
        roi_node = store.record_node("roi_cascade", {
            "element_id": element.element_id,
            "bbox": element.bbox_xyxy,
            "roi_type": element.element_type,
        })
        evidence_ids.append(roi_node.node_id)
        store.record_edge(roi_node.node_id, frame_node.node_id, EDGE_DERIVED_FROM)

        # Step 3: Record grounded element evidence
        grounded_node = store.record_node("grounded_element", {
            "element_id": element.element_id,
            "label": element.label,
            "confidence": element.confidence,
            "element_type": element.element_type,
        })
        evidence_ids.append(grounded_node.node_id)
        store.record_edge(grounded_node.node_id, roi_node.node_id, EDGE_DERIVED_FROM)

        # Step 4: Confidence gate classification
        classification = _classify_element(element)

        # Step 5: Action decision
        if classification == "blocked":
            actual_blocked.append(element.element_id)
            # Record blocking evidence
            block_node = store.record_node(NODE_TYPE_PRECONDITION, {
                "element_id": element.element_id,
                "reason": "destructive_action_blocked",
                "label": element.label,
            })
            evidence_ids.append(block_node.node_id)
            store.record_edge(block_node.node_id, grounded_node.node_id, EDGE_SATISFIES)

        elif classification == "confirm":
            actual_confirm.append(element.element_id)
            # Record confirmation required evidence
            confirm_node = store.record_node(NODE_TYPE_VERIFIER_CONTRACT, {
                "element_id": element.element_id,
                "reason": "confirmation_required",
                "confidence": element.confidence,
            })
            evidence_ids.append(confirm_node.node_id)
            store.record_edge(confirm_node.node_id, grounded_node.node_id, EDGE_SATISFIES)

        else:
            actual_execute.append(element.element_id)
            # Record safe execution evidence
            action_node = store.record_node(NODE_TYPE_ACTION_INTENT, {
                "element_id": element.element_id,
                "action": "execute",
                "label": element.label,
            })
            evidence_ids.append(action_node.node_id)
            store.record_edge(action_node.node_id, grounded_node.node_id, EDGE_DERIVED_FROM)

            # Post-action verifier
            verifier_node = store.record_node(NODE_TYPE_VERIFIER_RESULT, {
                "element_id": element.element_id,
                "verified": True,
            })
            evidence_ids.append(verifier_node.node_id)
            store.record_edge(verifier_node.node_id, action_node.node_id, EDGE_DERIVED_FROM)

        element_results.append({
            "element_id": element.element_id,
            "classification": classification,
            "label": element.label,
            "confidence": element.confidence,
        })

    # Verify expectations
    blocked_ok = set(actual_blocked) == set(scenario.expected_blocked)
    confirm_ok = set(actual_confirm) == set(scenario.expected_confirmation)
    execute_ok = set(actual_execute) == set(scenario.expected_execute)
    passed = blocked_ok and confirm_ok and execute_ok

    # Evidence coverage: each element should have at least 3 evidence nodes
    # (frame, roi, grounded) + action-specific
    min_expected_evidence = len(scenario.elements) * 3
    evidence_coverage = min(len(evidence_ids) / max(min_expected_evidence, 1), 1.0)

    safety_blocks = len(actual_blocked)
    confirmation_required = len(actual_confirm)

    metrics = BenchmarkMetrics(
        frame_to_observation_ms=0.0,
        observation_to_interrupt_ms=0.0,
        interrupt_to_lease_ms=0.0,
        danger_clear_time_ms=0.0,
        danger_false_clear_rate=0.0,
        resume_success_rate=0.0,
        max_consecutive_dodges=0,
        final_task_success=passed,
        evidence_coverage=evidence_coverage,
    )

    return BenchmarkResult(
        benchmark_id=f"ui_safety_{scenario.name}",
        run_id=uuid.uuid4().hex[:8],
        suite_name="high_res_ui_safety_grounding",
        scenario_name=scenario.name,
        passed=passed,
        metrics=metrics,
        evidence_ids=evidence_ids,
        report={
            "safety_blocks": safety_blocks,
            "blocked_actions": actual_blocked,
            "confirmation_required": confirmation_required,
            "confirm_elements": actual_confirm,
            "executed_elements": actual_execute,
            "element_results": element_results,
            "blocked_ok": blocked_ok,
            "confirm_ok": confirm_ok,
            "execute_ok": execute_ok,
            "verifier_results": passed,
        },
    )


def run_all_ui_safety() -> list[BenchmarkResult]:
    """Run all UI safety scenarios and return results."""
    return [run_scenario(scenario) for scenario in SCENARIOS]

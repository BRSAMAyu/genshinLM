"""Bridges between kernel claims and the claim-centric runtime types."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from agent_kernel.types import (
    ActionableElement,
    ClaimEvidence,
    DesktopNode,
    DesktopTree,
    SceneObject,
    SemanticObservation,
    StateDeltaClaim as KernelStateDeltaClaim,
)

_DESKTOP_ROLES = {
    "button", "list_item", "dialog_text", "dialog_option", "quest_entry",
    "reward_item", "teleport_point", "icon", "slider", "modal", "panel", "unknown",
}
_DESKTOP_SOURCES = {"ocr", "template_match", "vlm_grounding", "heuristic"}
_SCENE_KINDS = {"npc", "enemy", "waypoint", "item", "door", "puzzle_part", "button", "dialog_option", "unknown"}


@dataclass(frozen=True, slots=True)
class ClaimBridgeResult:
    kernel_claim: KernelStateDeltaClaim
    runtime_claim: Any | None = None


class KernelClaimBridge:
    """Translate claim objects without making the kernel depend on runtime."""

    def from_runtime_state_delta(self, claim: Any) -> KernelStateDeltaClaim:
        """Convert runtime.claim_runtime.StateDeltaClaim into kernel claim form."""
        status = getattr(claim, "status", "")
        claimed_delta = getattr(claim, "claimed_delta", {}) or {}
        evidence_refs = tuple(str(v) for v in getattr(claim, "evidence_refs", []) or [])
        evidence = tuple(
            ClaimEvidence(
                claim_id=str(getattr(claim, "claim_id", "")),
                evidence_type="runtime_evidence_ref",
                value=ref,
                confidence=float(getattr(claim, "confidence", 0.0) or 0.0),
                source="runtime.claim_runtime",
            )
            for ref in evidence_refs
        )
        return KernelStateDeltaClaim(
            claim_id=str(getattr(claim, "claim_id", "")),
            expected_state=str(claimed_delta.get("expected_state", claimed_delta.get("goal", ""))),
            observed_state=str(claimed_delta.get("observed_state", "")),
            delta_description=str(claimed_delta.get("description", getattr(claim, "claim_type", ""))),
            verified=status in {"verified", "audited", "locked"},
            confidence=float(getattr(claim, "confidence", 0.0) or 0.0),
            evidence=evidence,
            attributions=evidence_refs,
            timestamp=float(getattr(claim, "created_at", 0.0) or 0.0),
        )

    def to_runtime_state_delta(
        self,
        claim: KernelStateDeltaClaim,
        *,
        mission_id: str,
        node_id: str,
        skill_id: str,
        claim_type: str = "generic_unknown",
        input_claims: list[str] | None = None,
    ) -> Any:
        """Convert a kernel claim into runtime.claim_runtime.StateDeltaClaim."""
        from runtime.claim_runtime import StateDeltaClaim as RuntimeStateDeltaClaim

        return RuntimeStateDeltaClaim(
            claim_id=claim.claim_id,
            mission_id=mission_id,
            node_id=node_id,
            skill_id=skill_id,
            claim_type=claim_type,
            claimed_delta={
                "expected_state": claim.expected_state,
                "observed_state": claim.observed_state,
                "description": claim.delta_description,
            },
            status="verified" if claim.verified else "asserted",
            confidence=claim.confidence,
            evidence_refs=list(claim.attributions),
            input_claims=input_claims or [],
        )

    def screen_claim_to_observation(self, claim: Any) -> SemanticObservation:
        """Convert planning.screen_state_claim.ScreenStateClaim to SemanticObservation."""
        timestamp = float(getattr(claim, "timestamp", 0.0) or time.perf_counter())
        nodes: list[DesktopNode] = []
        actionables: list[ActionableElement] = []
        for element in getattr(claim, "ui_elements", ()) or ():
            bbox = tuple(getattr(element, "bbox_norm", (0.0, 0.0, 0.0, 0.0)))
            role = str(getattr(element, "role", "unknown"))
            label = str(getattr(element, "text", ""))
            confidence = float(getattr(element, "confidence", 0.0) or 0.0)
            node_role = role if role in _DESKTOP_ROLES else "unknown"
            node_source = str(getattr(element, "source", "unknown"))
            nodes.append(DesktopNode(
                node_id=str(getattr(element, "element_id", f"node_{len(nodes)}")),
                role=node_role,
                label=label,
                bbox=bbox,
                confidence=confidence,
                source=node_source if node_source in _DESKTOP_SOURCES else "heuristic",
            ))
            actionables.append(ActionableElement(
                element_type=role,
                label=label,
                bbox=bbox,
                confidence=confidence,
            ))
        visible_objects = tuple(
            SceneObject(
                object_id=str(item.get("id", f"obj_{index}")),
                kind=item.get("kind", "unknown") if item.get("kind", "unknown") in _SCENE_KINDS else "unknown",
                label=str(item.get("label", "")),
                confidence=float(item.get("confidence", 0.0) or 0.0),
                source=str(item.get("source", "screen_claim")),
            )
            for index, item in enumerate(getattr(claim, "visible_objects", ()) or ())
            if isinstance(item, dict)
        )
        desktop_tree = DesktopTree(
            timestamp=timestamp,
            screen_state=str(getattr(claim, "screen_state", "unknown")),
            nodes=tuple(nodes),
            is_modal_active=str(getattr(claim, "screen_state", "")) in {"dialog", "menu", "reward_screen"},
        )
        return SemanticObservation(
            timestamp=timestamp,
            frame_id=int(getattr(claim, "frame_id", 0) or 0),
            screen_state=str(getattr(claim, "screen_state", "unknown")),
            desktop_tree=desktop_tree,
            raw_ocr_text=" ".join(getattr(claim, "raw_ocr_texts", ()) or ()),
            vlm_description=str(getattr(claim, "scene_description", "")),
            scene_description=str(getattr(claim, "scene_description", "")),
            actionable_elements=tuple(actionables),
            vlm_confidence=float(getattr(claim, "confidence", 0.0) or 0.0),
        )

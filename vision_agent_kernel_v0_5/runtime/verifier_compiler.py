from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from runtime.claim_adjudicator import ClaimRecipe, CORE_RECIPES


VerifierType = Literal[
    "screen_state_match",
    "screen_state_transition",
    "screen_state_stable",
    "element_appearance",
    "element_disappearance",
    "text_match",
    "regex_match",
    "anchor_exists",
    "anchor_not_exists",
    "color_region_change",
    "numeric_delta",
    "progress_threshold",
    "danger_score_below",
    "temporal_pattern_match",
    "composite",
]


@dataclass(frozen=True, slots=True)
class VerifierStep:
    type: VerifierType | str
    roi: str = ""
    contains: str = ""
    contains_any: list[str] = field(default_factory=list)
    state: str = ""
    from_state: str = ""
    to_state: str = ""
    anchor: str = ""
    frames: int = 0
    timeout_ms: int = 1500
    item: str = ""
    expected_delta: int | float = 0
    threshold: float = 0.0
    all_of: list["VerifierStep"] = field(default_factory=list)
    any_of: list["VerifierStep"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UncertaintyPolicyDecl:
    on_low_confidence: str = "resample"
    max_retries: int = 2


@dataclass(frozen=True, slots=True)
class VerifierBundle:
    claim_type: str
    primary: list[VerifierStep] = field(default_factory=list)
    secondary: list[VerifierStep] = field(default_factory=list)
    delayed_audit: list[VerifierStep] = field(default_factory=list)
    uncertainty_policy: UncertaintyPolicyDecl = field(default_factory=UncertaintyPolicyDecl)


class VerifierCompiler:
    """MVP: Lookup table from claim_type → VerifierBundle.

    Developers declare claims, VerifierCompiler auto-generates
    verification configuration (Section 9.5).

    MVP scope: lookup table only, no auto-reasoning.
    """

    def __init__(self, bundles: dict[str, VerifierBundle] | None = None) -> None:
        self._bundles: dict[str, VerifierBundle] = dict(bundles or {})
        self._custom_mappings: set[str] = set()

    def register_bundle(self, bundle: VerifierBundle, *, custom_mapping: bool = False) -> None:
        self._bundles[bundle.claim_type] = bundle
        if custom_mapping:
            self._custom_mappings.add(bundle.claim_type)

    def compile(self, claim_type: str, recipe: ClaimRecipe | None = None) -> VerifierBundle:
        if claim_type in self._bundles:
            return self._bundles[claim_type]
        if recipe is not None:
            return self._recipe_to_bundle(claim_type, recipe)
        return VerifierBundle(claim_type=claim_type)

    def is_custom_mapping(self, claim_type: str) -> bool:
        return claim_type in self._custom_mappings

    def _recipe_to_bundle(self, claim_type: str, recipe: ClaimRecipe) -> VerifierBundle:
        primary_steps: list[VerifierStep] = []
        for family in recipe.required_families:
            primary_steps.append(VerifierStep(
                type="text_match",
                roi=f"{family}_area",
                contains=family,
                timeout_ms=1500,
            ))
        secondary_steps: list[VerifierStep] = []
        for family in recipe.optional_families:
            step_type = "element_disappearance" if "disappear" in family else "anchor_exists"
            secondary_steps.append(VerifierStep(
                type=step_type,
                anchor=family,
                timeout_ms=2000,
            ))
        return VerifierBundle(
            claim_type=claim_type,
            primary=primary_steps,
            secondary=secondary_steps,
        )


CORE_BUNDLES: dict[str, VerifierBundle] = {
    "inventory_delta": VerifierBundle(
        claim_type="inventory_delta",
        primary=[
            VerifierStep(type="text_match", roi="toast_area", contains_any=["清心", "+1"], timeout_ms=1500),
        ],
        secondary=[
            VerifierStep(type="element_disappearance", anchor="collect_prompt", timeout_ms=2000),
            VerifierStep(type="screen_state_stable", state="overworld", frames=5, timeout_ms=3000),
        ],
        delayed_audit=[
            VerifierStep(type="numeric_delta", item="qingxin", expected_delta=1),
        ],
        uncertainty_policy=UncertaintyPolicyDecl(on_low_confidence="resample_then_inventory_audit"),
    ),
    "screen_state_transition": VerifierBundle(
        claim_type="screen_state_transition",
        primary=[
            VerifierStep(type="screen_state_transition", from_state="", to_state="", timeout_ms=3000),
        ],
    ),
    "navigation_arrival": VerifierBundle(
        claim_type="navigation_arrival",
        primary=[
            VerifierStep(type="progress_threshold", threshold=0.95, timeout_ms=5000),
        ],
        secondary=[
            VerifierStep(type="screen_state_stable", state="overworld", frames=5, timeout_ms=3000),
            VerifierStep(type="anchor_exists", anchor="minimap", timeout_ms=2000),
        ],
    ),
    "combat_target_killed": VerifierBundle(
        claim_type="combat_target_killed",
        primary=[
            VerifierStep(type="danger_score_below", threshold=0.3, timeout_ms=3000),
        ],
        secondary=[
            VerifierStep(type="element_appearance", anchor="combat_reward", timeout_ms=5000),
        ],
    ),
    "collection_pickup": VerifierBundle(
        claim_type="collection_pickup",
        primary=[
            VerifierStep(type="text_match", roi="toast_area", contains_any=["清心", "+1"], timeout_ms=1500),
            VerifierStep(type="numeric_delta", item="qingxin", expected_delta=1),
        ],
        secondary=[
            VerifierStep(type="element_disappearance", anchor="collect_prompt", timeout_ms=2000),
        ],
        delayed_audit=[
            VerifierStep(type="numeric_delta", item="qingxin", expected_delta=1),
        ],
    ),
    "dialogue_advance": VerifierBundle(
        claim_type="dialogue_advance",
        primary=[
            VerifierStep(type="text_match", roi="dialog_area", contains="", timeout_ms=1500),
        ],
        secondary=[
            VerifierStep(type="anchor_exists", anchor="dialog_box", timeout_ms=1000),
        ],
    ),
    "teleport_loaded": VerifierBundle(
        claim_type="teleport_loaded",
        primary=[
            VerifierStep(type="element_disappearance", anchor="loading_spinner", timeout_ms=10000),
        ],
        secondary=[
            VerifierStep(type="screen_state_stable", state="overworld", frames=5, timeout_ms=3000),
        ],
    ),
    "danger_cleared": VerifierBundle(
        claim_type="danger_cleared",
        primary=[
            VerifierStep(type="danger_score_below", threshold=0.3, timeout_ms=3000),
        ],
        secondary=[
            VerifierStep(type="screen_state_stable", state="overworld", frames=3, timeout_ms=2000),
        ],
    ),
}

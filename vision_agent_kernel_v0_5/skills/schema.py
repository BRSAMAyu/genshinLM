"""Skill OS Schema — unified skill definition.

A SkillDef describes an executable skill with:
- Applicability: screen states, required anchors, required claims
- Steps: semantic action sequence with wait conditions
- Produced claims: what state changes the skill produces
- Belief templates: BAGEL beliefs that must be committed before execution
- Fallbacks: recovery recipes when execution fails
- Promotion: reliability thresholds for promotion ladder
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from runtime.claim_runtime import RiskLevel


SkillKind = Literal["procedure", "macro", "motor", "composite", "exploration"]
PromotionTier = Literal["raw_trace", "draft", "experimental", "candidate", "stable", "trusted"]
StepAction = Literal[
    "click_anchor", "click_text", "press_key", "select_list_item",
    "confirm_dialog", "wait_for", "observe", "navigate_to", "interact",
]


@dataclass(frozen=True, slots=True)
class SkillStep:
    """A single step in a skill's action sequence."""
    action: StepAction
    target: str = ""
    wait_until: str = ""
    timeout_ms: int = 5000
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillApplicability:
    """Conditions under which a skill can execute."""
    screen_states: tuple[str, ...] = ()
    required_anchors: tuple[str, ...] = ()
    required_claims: tuple[str, ...] = ()  # claim_type values


@dataclass(frozen=True, slots=True)
class SkillProducedClaim:
    """A claim produced by successful skill execution."""
    claim_type: str
    target: str = ""
    claim_role: str = "local"
    verifier_recipe: str = ""


@dataclass(frozen=True, slots=True)
class SkillBeliefTemplate:
    """BAGEL belief that must be committed before skill execution."""
    target_object: str
    causal_role: str
    hypothesis: str = ""
    falsification_condition: str = ""


@dataclass(frozen=True, slots=True)
class SkillFallback:
    """Recovery recipe or replan policy for skill failure."""
    recovery_recipe: str = ""
    replan_policy: str = ""


@dataclass(frozen=True, slots=True)
class PromotionConfig:
    """Thresholds for skill promotion between tiers."""
    min_replays: int = 3
    min_wilson_lower_bound: float = 0.70
    required_profiles: tuple[str, ...] = ("default_1920x1080",)


@dataclass(frozen=True, slots=True)
class SkillReliabilityContext:
    screen_state: str = ""
    resolution: str = ""
    capsule_id: str = ""
    team_state: str = ""
    resource_state: str = ""
    testbed_profile: str = ""
    skill_tier: str = ""


@dataclass(frozen=True, slots=True)
class SkillJitRegenerationPolicy:
    enabled: bool = True
    requires_probe: bool = True
    controlled_rollback_on_failure: bool = True


@dataclass(frozen=True, slots=True)
class SkillBagelProbePolicy:
    probe_family: str = ""
    max_non_decidable: int = 2
    tie_breaker_required: bool = False


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate a v1 skill dict to v2 schema.

    V1 → V2 adds: jit_regeneration_policy, bagel_probe_policy fields
    and normalises missing nested dicts to their defaults.
    """
    data = dict(data)
    data.setdefault("jit_regeneration_policy", {})
    data.setdefault("bagel_probe_policy", {})
    app = data.get("applicability", {})
    if not isinstance(app, dict):
        app = {"screen_states": (), "required_anchors": (), "required_claims": ()}
        data["applicability"] = app
    app.setdefault("required_claims", [])
    data["version"] = 2
    data.setdefault("belief_templates", [])
    data.setdefault("fallbacks", [])
    promo = data.get("promotion", {})
    if isinstance(promo, dict):
        promo.setdefault("min_replays", 3)
        promo.setdefault("min_wilson_lower_bound", 0.70)
        promo.setdefault("required_profiles", ["default_1920x1080"])
    rel = data.get("reliability_context", {})
    if isinstance(rel, dict):
        rel.setdefault("screen_state", "")
        rel.setdefault("resolution", "")
        rel.setdefault("capsule_id", "")
        rel.setdefault("team_state", "")
        rel.setdefault("resource_state", "")
        rel.setdefault("testbed_profile", "")
        rel.setdefault("skill_tier", "")
    return data


@dataclass(frozen=True, slots=True)
class SkillDef:
    """Unified skill definition.

    Serializable to/from dict for JSON/YAML storage and exchange.
    """
    skill_id: str
    version: int = 2
    capsule_id: str = "core"
    kind: SkillKind = "procedure"
    risk_level: RiskLevel = "medium"
    tier: PromotionTier = "draft"

    applicability: SkillApplicability = field(default_factory=SkillApplicability)
    steps: tuple[SkillStep, ...] = ()
    produced_claims: tuple[SkillProducedClaim, ...] = ()
    belief_templates: tuple[SkillBeliefTemplate, ...] = ()
    fallbacks: tuple[SkillFallback, ...] = ()
    promotion: PromotionConfig = field(default_factory=PromotionConfig)
    reliability_context: SkillReliabilityContext = field(default_factory=SkillReliabilityContext)
    jit_regeneration_policy: SkillJitRegenerationPolicy = field(default_factory=SkillJitRegenerationPolicy)
    bagel_probe_policy: SkillBagelProbePolicy = field(default_factory=SkillBagelProbePolicy)

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def skill_kind(self) -> SkillKind:
        return self.kind

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "capsule_id": self.capsule_id,
            "kind": self.kind,
            "risk_level": self.risk_level,
            "tier": self.tier,
            "applicability": {
                "screen_states": list(self.applicability.screen_states),
                "required_anchors": list(self.applicability.required_anchors),
                "required_claims": list(self.applicability.required_claims),
            },
            "steps": [
                {"action": s.action, "target": s.target, "wait_until": s.wait_until,
                 "timeout_ms": s.timeout_ms, "params": s.params}
                for s in self.steps
            ],
            "produced_claims": [
                {"claim_type": c.claim_type, "target": c.target,
                 "claim_role": c.claim_role, "verifier_recipe": c.verifier_recipe}
                for c in self.produced_claims
            ],
            "belief_templates": [
                {"target_object": bt.target_object, "causal_role": bt.causal_role,
                 "hypothesis": bt.hypothesis, "falsification_condition": bt.falsification_condition}
                for bt in self.belief_templates
            ],
            "fallbacks": [
                {"recovery_recipe": f.recovery_recipe, "replan_policy": f.replan_policy}
                for f in self.fallbacks
            ],
            "promotion": {
                "min_replays": self.promotion.min_replays,
                "min_wilson_lower_bound": self.promotion.min_wilson_lower_bound,
                "required_profiles": list(self.promotion.required_profiles),
            },
            "reliability_context": {
                "screen_state": self.reliability_context.screen_state,
                "resolution": self.reliability_context.resolution,
                "capsule_id": self.reliability_context.capsule_id,
                "team_state": self.reliability_context.team_state,
                "resource_state": self.reliability_context.resource_state,
                "testbed_profile": self.reliability_context.testbed_profile,
                "skill_tier": self.reliability_context.skill_tier,
            },
            "jit_regeneration_policy": {
                "enabled": self.jit_regeneration_policy.enabled,
                "requires_probe": self.jit_regeneration_policy.requires_probe,
                "controlled_rollback_on_failure": self.jit_regeneration_policy.controlled_rollback_on_failure,
            },
            "bagel_probe_policy": {
                "probe_family": self.bagel_probe_policy.probe_family,
                "max_non_decidable": self.bagel_probe_policy.max_non_decidable,
                "tie_breaker_required": self.bagel_probe_policy.tie_breaker_required,
            },
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillDef:
        # Schema migration
        version = data.get("version", 1)
        if version < 2:
            data = _migrate_v1_to_v2(data)
        app = data.get("applicability", {})
        promo = data.get("promotion", {})
        rel = data.get("reliability_context", {})
        jit = data.get("jit_regeneration_policy", {})
        probe = data.get("bagel_probe_policy", {})
        return cls(
            skill_id=data["skill_id"],
            version=data.get("version", 1),
            capsule_id=data.get("capsule_id", "core"),
            kind=data.get("kind", "procedure"),
            risk_level=data.get("risk_level", "medium"),
            tier=data.get("tier", "draft"),
            applicability=SkillApplicability(
                screen_states=tuple(app.get("screen_states", [])),
                required_anchors=tuple(app.get("required_anchors", [])),
                required_claims=tuple(app.get("required_claims", [])),
            ),
            steps=tuple(
                SkillStep(
                    action=s["action"], target=s.get("target", ""),
                    wait_until=s.get("wait_until", ""), timeout_ms=s.get("timeout_ms", 5000),
                    params=s.get("params", {}),
                )
                for s in data.get("steps", [])
            ),
            produced_claims=tuple(
                SkillProducedClaim(
                    claim_type=c["claim_type"], target=c.get("target", ""),
                    claim_role=c.get("claim_role", "local"),
                    verifier_recipe=c.get("verifier_recipe", ""),
                )
                for c in data.get("produced_claims", [])
            ),
            belief_templates=tuple(
                SkillBeliefTemplate(
                    target_object=bt["target_object"], causal_role=bt["causal_role"],
                    hypothesis=bt.get("hypothesis", ""),
                    falsification_condition=bt.get("falsification_condition", ""),
                )
                for bt in data.get("belief_templates", [])
            ),
            fallbacks=tuple(
                SkillFallback(
                    recovery_recipe=f.get("recovery_recipe", ""),
                    replan_policy=f.get("replan_policy", ""),
                )
                for f in data.get("fallbacks", [])
            ),
            promotion=PromotionConfig(
                min_replays=promo.get("min_replays", 3),
                min_wilson_lower_bound=promo.get("min_wilson_lower_bound", 0.70),
                required_profiles=tuple(promo.get("required_profiles", ["default_1920x1080"])),
            ),
            reliability_context=SkillReliabilityContext(
                screen_state=rel.get("screen_state", ""),
                resolution=rel.get("resolution", ""),
                capsule_id=rel.get("capsule_id", ""),
                team_state=rel.get("team_state", ""),
                resource_state=rel.get("resource_state", ""),
                testbed_profile=rel.get("testbed_profile", ""),
                skill_tier=rel.get("skill_tier", ""),
            ),
            jit_regeneration_policy=SkillJitRegenerationPolicy(
                enabled=jit.get("enabled", True),
                requires_probe=jit.get("requires_probe", True),
                controlled_rollback_on_failure=jit.get("controlled_rollback_on_failure", True),
            ),
            bagel_probe_policy=SkillBagelProbePolicy(
                probe_family=probe.get("probe_family", ""),
                max_non_decidable=probe.get("max_non_decidable", 2),
                tie_breaker_required=probe.get("tie_breaker_required", False),
            ),
            metadata=data.get("metadata", {}),
        )

from __future__ import annotations

from skills.schema import (
    SkillBagelProbePolicy,
    SkillDef,
    SkillJitRegenerationPolicy,
    SkillReliabilityContext,
)


def test_skill_v12_fields_roundtrip() -> None:
    skill = SkillDef(
        skill_id="motor_heading_servo",
        kind="motor",
        reliability_context=SkillReliabilityContext(
            screen_state="overworld",
            resolution="1920x1080",
            capsule_id="genshin_like_testbed",
            team_state="starter",
            resource_state="low",
            testbed_profile="pseudo3d",
            skill_tier="candidate",
        ),
        jit_regeneration_policy=SkillJitRegenerationPolicy(enabled=True, requires_probe=True),
        bagel_probe_policy=SkillBagelProbePolicy(probe_family="heading_servo_progress"),
    )
    restored = SkillDef.from_dict(skill.to_dict())
    assert restored.kind == "motor"
    assert restored.skill_kind == "motor"
    assert restored.reliability_context.testbed_profile == "pseudo3d"
    assert restored.bagel_probe_policy.probe_family == "heading_servo_progress"

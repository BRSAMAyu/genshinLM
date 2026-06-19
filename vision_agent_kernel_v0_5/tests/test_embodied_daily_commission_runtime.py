from __future__ import annotations

from planning.screen_state_claim import ScreenStateClaim, UIElementClaim

from agent_kernel.claim_bridge import KernelClaimBridge
from agent_kernel.dialogue_controller import DialogueController
from agent_kernel.embodied_runtime import (
    DailyCommissionDryRunRuntime,
    DailyCommissionObjective,
    HybridOpenWorldNavigator,
    NavigationFrame,
    RealTimeCombatPolicy,
    TeamCombatRuntime,
    TeamMemberRuntime,
)
from agent_kernel.skill_lookup import KernelSkillRecipeLookup
from agent_kernel.types import AgentGoal, DesktopNode, DesktopTree, SkillRecipe, SkillStep, StateDeltaClaim, ThreatSignal


def _team(active_hp: float = 1.0, healer_ready: bool = True, food_available: bool = True) -> TeamCombatRuntime:
    return TeamCombatRuntime(
        active_slot=1,
        food_available=food_available,
        members=(
            TeamMemberRuntime(1, "driver", hp_pct=active_hp, skill_ready=True, burst_ready=False, summary="on-field driver"),
            TeamMemberRuntime(2, "sub_dps", hp_pct=1.0, skill_ready=True, burst_ready=True, summary="off-field damage"),
            TeamMemberRuntime(3, "healer", hp_pct=1.0, skill_ready=healer_ready, burst_ready=False, summary="team recovery"),
            TeamMemberRuntime(4, "support", hp_pct=1.0, skill_ready=True, burst_ready=False, summary="buff support"),
        ),
    )


def test_hybrid_navigation_uses_minimap_when_target_is_not_visible() -> None:
    action = HybridOpenWorldNavigator().decide(
        NavigationFrame(target_label="commission marker", minimap_bearing_deg=47.0, distance_m=120.0),
    )

    assert action.kind == "navigation"
    assert action.intent == "steer_by_minimap"
    assert action.param("bearing_deg") == "47.0"


def test_hybrid_navigation_turns_then_engages_visible_enemy() -> None:
    nav = HybridOpenWorldNavigator()

    turn = nav.decide(NavigationFrame(
        target_label="enemy group",
        target_bbox_norm=(0.10, 0.40, 0.20, 0.70),
        target_confidence=0.8,
        target_kind="enemy",
        distance_m=16.0,
    ))
    engage = nav.decide(NavigationFrame(
        target_label="enemy group",
        target_bbox_norm=(0.46, 0.40, 0.54, 0.70),
        target_confidence=0.8,
        target_kind="enemy",
        distance_m=2.5,
    ))

    assert turn.intent == "turn_towards_target"
    assert engage.intent == "enter_combat"


def test_combat_policy_prioritizes_dodge_over_rotation() -> None:
    action = RealTimeCombatPolicy().decide(
        (ThreatSignal("projectile", 0.91, direction_degrees=12.0, time_to_impact_ms=180),),
        _team(),
    )

    assert action.intent == "dodge_reflex"
    assert action.priority == 100
    assert action.expected_claim_type == "danger_cleared"


def test_combat_policy_uses_food_when_healer_is_unavailable() -> None:
    action = RealTimeCombatPolicy().decide((), _team(active_hp=0.18, healer_ready=False))

    assert action.intent == "use_emergency_food"
    assert action.param("slot") == "1"


def test_daily_commission_dry_run_closes_full_loop() -> None:
    runtime = DailyCommissionDryRunRuntime()
    objectives = (
        DailyCommissionObjective("c1", "combat", "region_a", "wp_a", "enemy group"),
        DailyCommissionObjective("c2", "interaction", "region_b", "wp_b", "npc target"),
        DailyCommissionObjective("c3", "dialogue", "region_c", "wp_c", "quest npc"),
        DailyCommissionObjective("c4", "puzzle", "region_d", "wp_d", "element monument", "activate visible monuments"),
    )
    trace = runtime.run(objectives, frames_by_objective={}, team=_team())

    intents = trace.intents()
    assert trace.completed is True
    assert trace.final_phase == "complete"
    assert "open_quest_list" in intents
    assert intents.count("teleport_to_waypoint") == 4
    assert "steer_by_minimap" in intents
    assert "turn_towards_target" in intents
    assert "dodge_reflex" in intents
    assert "solve_visual_puzzle_or_escalate" in intents
    assert "claim_adventure_guild_daily_reward" in intents
    assert "refresh_expeditions" in intents
    assert len(trace.claims) == len(trace.actions)
    assert all(claim.verified for claim in trace.claims)


def test_kernel_skill_recipe_lookup_ingests_capsule_library() -> None:
    lookup = KernelSkillRecipeLookup.from_capsule_library({
        "daily_commission": {
            "skill_id": "daily_commission_loop",
            "title": "Daily Commission Loop",
            "goal_template": "complete daily commissions",
            "steps": [
                {"step_id": "open", "intent": "open_quest_list", "target_query": "quest list"},
                {"step_id": "claim", "intent": "claim_rewards", "target_query": "adventure guild"},
            ],
            "verifiers": ["daily_rewards_claimed"],
        }
    })

    recipe = lookup.lookup("daily_commission")
    assert recipe.skill_id == "daily_commission_loop"
    assert recipe.steps[0].intent == "open_quest_list"
    assert lookup.lookup_recipe("daily_commission_loop")["verifiers"] == ["daily_rewards_claimed"]
    assert lookup.find_applicable("daily", AgentGoal("daily_commission", "complete daily", "rewards")) == [recipe]


def test_kernel_skill_recipe_lookup_rejects_missing_capability() -> None:
    lookup = KernelSkillRecipeLookup.with_recipes((
        SkillRecipe(
            "combat_loop",
            "Combat Loop",
            "win combat",
            steps=(SkillStep("s1", "combo_normal_attack", "enemy"),),
        ),
    ))

    try:
        lookup.lookup("unknown")
    except KeyError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("missing capability should raise KeyError")


def test_claim_bridge_converts_screen_and_runtime_claims() -> None:
    bridge = KernelClaimBridge()
    screen_claim = ScreenStateClaim(
        game_id="sandbox",
        screen_state="dialog",
        confidence=0.9,
        source="hybrid",
        ui_elements=(
            UIElementClaim("choice_1", "dialog_option", "Claim rewards", (0.4, 0.5, 0.7, 0.6), 0.88, "ocr", True),
        ),
        raw_ocr_texts=("Claim rewards",),
        scene_description="dialog with reward option",
        frame_id=12,
    )
    observation = bridge.screen_claim_to_observation(screen_claim)
    assert observation.screen_state == "dialog"
    assert observation.desktop_tree is not None
    assert observation.desktop_tree.nodes[0].role == "dialog_option"
    assert observation.actionable_elements[0].label == "Claim rewards"

    kernel_claim = StateDeltaClaim(
        "claim_1",
        expected_state="inventory_delta",
        observed_state="inventory_delta",
        verified=True,
        confidence=0.91,
        attributions=("frame_12",),
    )
    runtime_claim = bridge.to_runtime_state_delta(
        kernel_claim,
        mission_id="daily",
        node_id="claim_rewards",
        skill_id="daily_commission_loop",
        claim_type="inventory_delta",
    )
    round_tripped = bridge.from_runtime_state_delta(runtime_claim)
    assert round_tripped.verified is True
    assert round_tripped.expected_state == "inventory_delta"
    assert round_tripped.attributions == ("frame_12",)


def test_dialogue_controller_accepts_desktop_tree_options() -> None:
    controller = DialogueController()
    tree = DesktopTree(
        timestamp=1.0,
        screen_state="dialog",
        nodes=(
            DesktopNode(
                node_id="opt_1",
                role="dialog_option",
                label="dialog option: continue",
                bbox=(0.4, 0.4, 0.7, 0.5),
                confidence=0.8,
            ),
        ),
    )

    assert controller.is_option_present(tree) is True
    best = controller.select_best_option(tree)
    assert best is not None
    assert best["option_id"] == "opt_1"

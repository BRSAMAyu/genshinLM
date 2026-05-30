"""Tests for quest mechanism router and quest UI manager."""
from __future__ import annotations

import pytest

from planning.quest_mechanism_router import (
    ARBreakthroughHandler,
    ARBreakthroughState,
    AR_BREAKTHROUGH_DOMAINS,
    DreamHandler,
    DreamState,
    DomainQuestHandler,
    DomainQuestState,
    EscortHandler,
    EscortState,
    EventQuestHandler,
    EventQuestState,
    HangoutBranch,
    HangoutHandler,
    HangoutState,
    InvestigationHandler,
    InvestigationState,
    MechanismDecision,
    QuestMechanismRouter,
    QuestMechanismType,
    StealthHandler,
    StealthState,
    TimedHandler,
    TimedState,
)
from planning.quest_ui_manager import (
    CommissionInfo,
    CommissionManager,
    NPCOccupationHandler,
    QuestCategory,
    QuestCompletionDetector,
    QuestEntry,
    QuestLogManager,
    QuestStatus,
    QuestUIManager,
    WorldQuestDiscovery,
)


# ---------------------------------------------------------------------------
# Quest Mechanism Router tests
# ---------------------------------------------------------------------------

class TestStealthHandler:
    def test_detected_hides(self) -> None:
        handler = StealthHandler()
        state = StealthState(is_detected=True)
        decision = handler.evaluate(state)
        assert decision.action == "hide"
        assert decision.priority == 0

    def test_near_detection_waits(self) -> None:
        handler = StealthHandler()
        state = StealthState(detection_level=0.9)
        decision = handler.evaluate(state)
        assert decision.action == "hide"

    def test_suspicious_waits(self) -> None:
        handler = StealthHandler()
        state = StealthState(detection_level=0.6)
        decision = handler.evaluate(state)
        assert decision.action == "wait"

    def test_clear_proceeds(self) -> None:
        handler = StealthHandler()
        state = StealthState(target_position=(100.0, 200.0))
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert decision.target == (100.0, 200.0)

    def test_update_from_screen(self) -> None:
        handler = StealthHandler()
        state = StealthState()
        updated = handler.update_from_screen(state, [(50, 60)], 0.3)
        assert len(updated.guard_positions) == 1
        assert updated.detection_level == 0.3
        assert not updated.is_detected


class TestEscortHandler:
    def test_npc_critical_protect(self) -> None:
        handler = EscortHandler()
        state = EscortState(npc_health_ratio=0.2)
        decision = handler.evaluate(state)
        assert decision.action == "protect"
        assert decision.priority == 0

    def test_threats_nearby_fight(self) -> None:
        handler = EscortHandler()
        state = EscortState(threats_nearby=3)
        decision = handler.evaluate(state)
        assert decision.action == "fight"

    def test_npc_moving_follow(self) -> None:
        handler = EscortHandler()
        state = EscortState(npc_is_moving=True, destination=(100, 200))
        decision = handler.evaluate(state)
        assert decision.action == "proceed"

    def test_update_from_screen(self) -> None:
        handler = EscortHandler()
        state = EscortState()
        updated = handler.update_from_screen(state, (10, 20), 0.8, True, 2)
        assert updated.npc_position == (10, 20)
        assert updated.npc_health_ratio == 0.8
        assert updated.threats_nearby == 2


class TestTimedHandler:
    def test_critical_time_speeds(self) -> None:
        handler = TimedHandler()
        state = TimedState(time_remaining_sec=20, objectives_completed=0,
                           objectives_total=1, is_active=True)
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert decision.params.get("speed_mode") is True

    def test_all_done(self) -> None:
        handler = TimedHandler()
        state = TimedState(time_remaining_sec=100, objectives_completed=3,
                           objectives_total=3, is_active=True)
        decision = handler.evaluate(state)
        assert decision.action == "wait"

    def test_not_active(self) -> None:
        handler = TimedHandler()
        state = TimedState(is_active=False)
        decision = handler.evaluate(state)
        assert decision.priority == 50


class TestInvestigationHandler:
    def test_all_clues_found(self) -> None:
        handler = InvestigationHandler()
        state = InvestigationState(clues_found=["a", "b"], clues_total=2)
        decision = handler.evaluate(state)
        assert decision.action == "proceed"

    def test_searching(self) -> None:
        handler = InvestigationHandler()
        state = InvestigationState(clues_total=3, current_area="meropide")
        decision = handler.evaluate(state)
        assert decision.action == "search"

    def test_update_adds_clue(self) -> None:
        handler = InvestigationHandler()
        state = InvestigationState(clues_total=2)
        updated = handler.update_from_screen(state, new_clue="evidence_1")
        assert "evidence_1" in updated.clues_found


class TestDreamHandler:
    def test_exit_found(self) -> None:
        handler = DreamHandler()
        state = DreamState(exit_found=True)
        decision = handler.evaluate(state)
        assert decision.action == "exit"

    def test_environment_changed(self) -> None:
        handler = DreamHandler()
        state = DreamState(is_dream=True, environment_changed=True, cycle_number=2)
        decision = handler.evaluate(state)
        assert decision.action == "search"

    def test_cycle_increment(self) -> None:
        handler = DreamHandler()
        state = DreamState(is_dream=False)
        updated = handler.update_from_screen(state, is_dream_env=True,
                                             env_changed=True, exit_visible=False)
        assert updated.cycle_number == 2
        assert updated.is_dream


class TestDomainQuestHandler:
    def test_entrance_phase(self) -> None:
        handler = DomainQuestHandler()
        state = DomainQuestState(phase="entrance")
        decision = handler.evaluate(state)
        assert decision.action == "proceed"

    def test_combat_with_enemies(self) -> None:
        handler = DomainQuestHandler()
        state = DomainQuestState(phase="combat", enemies_remaining=5)
        decision = handler.evaluate(state)
        assert decision.action == "fight"

    def test_boss_phase(self) -> None:
        handler = DomainQuestHandler()
        state = DomainQuestState(phase="boss")
        decision = handler.evaluate(state)
        assert decision.action == "fight"
        assert decision.priority == 0

    def test_completion_with_resin(self) -> None:
        handler = DomainQuestHandler()
        state = DomainQuestState(phase="completion", resin_to_claim=40)
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert decision.params.get("use_resin") == 40


class TestARBreakthroughHandler:
    def test_breakthrough_needed(self) -> None:
        handler = ARBreakthroughHandler()
        state = ARBreakthroughState(target_ar=25, is_active=True)
        decision = handler.evaluate(state)
        assert decision.action == "fight"
        assert decision.params.get("domain") is not None

    def test_check_ar_breakthrough(self) -> None:
        handler = ARBreakthroughHandler()
        state = handler.check_ar_breakthrough_needed(current_ar=25, ar_cap=25)
        assert state.is_active
        assert state.target_ar == 25

    def test_no_breakthrough(self) -> None:
        handler = ARBreakthroughHandler()
        state = handler.check_ar_breakthrough_needed(current_ar=20, ar_cap=25)
        assert not state.is_active

    def test_breakthrough_domains_exist(self) -> None:
        assert 25 in AR_BREAKTHROUGH_DOMAINS
        assert 35 in AR_BREAKTHROUGH_DOMAINS
        assert 45 in AR_BREAKTHROUGH_DOMAINS
        assert 50 in AR_BREAKTHROUGH_DOMAINS


class TestQuestMechanismRouter:
    def test_route_stealth(self) -> None:
        router = QuestMechanismRouter()
        router._stealth_state.is_detected = True
        decision = router.route(QuestMechanismType.STEALTH)
        assert decision.action == "hide"

    def test_route_standard(self) -> None:
        router = QuestMechanismRouter()
        decision = router.route(QuestMechanismType.STANDARD)
        assert decision.action == "proceed"

    def test_identify_mechanism_stealth(self) -> None:
        router = QuestMechanismRouter()
        result = router.identify_mechanism({"tags": ["stealth"]})
        assert result == QuestMechanismType.STEALTH

    def test_identify_mechanism_domain(self) -> None:
        router = QuestMechanismRouter()
        result = router.identify_mechanism({"type": "domain"})
        assert result == QuestMechanismType.DOMAIN

    def test_identify_mechanism_default(self) -> None:
        router = QuestMechanismRouter()
        result = router.identify_mechanism({})
        assert result == QuestMechanismType.STANDARD

    def test_get_state(self) -> None:
        router = QuestMechanismRouter()
        state = router.get_state(QuestMechanismType.TIMED)
        assert isinstance(state, TimedState)


# ---------------------------------------------------------------------------
# Quest UI Manager tests
# ---------------------------------------------------------------------------

class TestQuestLogManager:
    def test_add_and_track(self) -> None:
        mgr = QuestLogManager()
        entry = QuestEntry("q1", "Test Quest", QuestCategory.ARCHON)
        mgr.update_quest(entry)
        mgr.set_tracked("q1")
        assert mgr.tracked_quest is not None
        assert mgr.tracked_quest.quest_id == "q1"

    def test_mark_completed(self) -> None:
        mgr = QuestLogManager()
        entry = QuestEntry("q1", "Test", QuestCategory.ARCHON, is_tracked=True)
        mgr.update_quest(entry)
        mgr.mark_completed("q1")
        assert mgr.tracked_quest is None

    def test_active_quests(self) -> None:
        mgr = QuestLogManager()
        mgr.update_quest(QuestEntry("q1", "Active", QuestCategory.ARCHON,
                                     status=QuestStatus.ACTIVE))
        mgr.update_quest(QuestEntry("q2", "Done", QuestCategory.ARCHON,
                                     status=QuestStatus.COMPLETED))
        active = mgr.active_quests
        assert len(active) == 1
        assert active[0].quest_id == "q1"

    def test_browse_category(self) -> None:
        mgr = QuestLogManager()
        mgr.update_quest(QuestEntry("q1", "Archon", QuestCategory.ARCHON))
        mgr.update_quest(QuestEntry("q2", "World", QuestCategory.WORLD))
        archon = mgr.browse_category(QuestCategory.ARCHON)
        assert len(archon) == 1

    def test_save_state(self) -> None:
        mgr = QuestLogManager()
        mgr.update_quest(QuestEntry("q1", "Test", QuestCategory.ARCHON,
                                     status=QuestStatus.ACTIVE, is_tracked=True))
        state = mgr.save_state()
        assert "q1" in state["quests"]
        assert state["tracked"] == "q1"


class TestWorldQuestDiscovery:
    def test_discover_and_accept(self) -> None:
        wq = WorldQuestDiscovery()
        entry = wq.discover_quest("NPC_A", (100, 200), "Clear the Ruins")
        assert len(wq.pending_quests) == 1
        wq.accept_quest(entry.quest_id)
        assert len(wq.pending_quests) == 0
        assert entry.status == QuestStatus.ACTIVE

    def test_decline(self) -> None:
        wq = WorldQuestDiscovery()
        entry = wq.discover_quest("NPC_B", (50, 60), "Help Needed")
        wq.decline_quest(entry.quest_id)
        assert len(wq.pending_quests) == 0


class TestCommissionManager:
    def test_all_complete(self) -> None:
        mgr = CommissionManager()
        for i in range(4):
            info = CommissionInfo(f"comm_{i}", f"Commission {i}", is_complete=True)
            mgr.add_commission(info)
        assert mgr.all_complete

    def test_incomplete(self) -> None:
        mgr = CommissionManager()
        mgr.add_commission(CommissionInfo("c1", "C1", is_complete=True))
        mgr.add_commission(CommissionInfo("c2", "C2", is_complete=False))
        assert len(mgr.incomplete_commissions) == 1

    def test_katheryne_reward(self) -> None:
        mgr = CommissionManager()
        for i in range(4):
            mgr.add_commission(CommissionInfo(f"c{i}", f"C{i}", is_complete=True))
        assert mgr.should_claim_katheryne()
        primos = mgr.claim_katheryne_reward()
        assert primos == 20
        assert not mgr.should_claim_katheryne()

    def test_reset_daily(self) -> None:
        mgr = CommissionManager()
        mgr.add_commission(CommissionInfo("c1", "C1"))
        mgr.reset_daily()
        assert len(mgr.incomplete_commissions) == 0


class TestQuestCompletionDetector:
    def test_quest_complete_screen(self) -> None:
        detector = QuestCompletionDetector()
        event = detector.check_completion("quest_complete", "Prologue Act I Complete")
        assert event is not None
        assert event.rewards_claimed is False

    def test_reward_screen(self) -> None:
        detector = QuestCompletionDetector()
        event = detector.check_completion("reward_screen")
        assert event is not None
        assert event.rewards_claimed is True

    def test_notification(self) -> None:
        detector = QuestCompletionDetector()
        event = detector.check_completion("world_hud",
                                          notifications=["Quest Complete!"])
        assert event is not None

    def test_no_completion(self) -> None:
        detector = QuestCompletionDetector()
        event = detector.check_completion("world_hud")
        assert event is None


class TestNPCOccupationHandler:
    def test_occupied(self) -> None:
        handler = NPCOccupationHandler()
        handler.mark_occupied("NPC_X", "q_block")
        assert not handler.is_available("NPC_X")
        assert handler.get_blocking_quest("NPC_X") == "q_block"

    def test_available(self) -> None:
        handler = NPCOccupationHandler()
        assert handler.is_available("NPC_Y")

    def test_resolve_conflict(self) -> None:
        handler = NPCOccupationHandler()
        handler.mark_occupied("NPC_Z", "q_block")
        quests = [QuestEntry("q_block", "Blocking Quest", QuestCategory.WORLD,
                              status=QuestStatus.ACTIVE)]
        result = handler.resolve_conflict("NPC_Z", quests)
        assert result["action"] == "complete_blocking_quest"

    def test_release(self) -> None:
        handler = NPCOccupationHandler()
        handler.mark_occupied("NPC_W", "q1")
        handler.mark_available("NPC_W")
        assert handler.is_available("NPC_W")


class TestQuestUIManager:
    def test_commission_priority(self) -> None:
        mgr = QuestUIManager()
        mgr.commission_manager.add_commission(
            CommissionInfo("c1", "Combat Commission"))
        action = mgr.get_next_action(25)
        assert action["action"] == "complete_commission"

    def test_katheryne_after_commissions(self) -> None:
        mgr = QuestUIManager()
        for i in range(4):
            mgr.commission_manager.add_commission(
                CommissionInfo(f"c{i}", f"C{i}", is_complete=True))
        action = mgr.get_next_action(25)
        assert action["action"] == "claim_katheryne_reward"

    def test_tracked_quest_priority(self) -> None:
        mgr = QuestUIManager()
        for i in range(4):
            mgr.commission_manager.add_commission(
                CommissionInfo(f"c{i}", f"C{i}", is_complete=True))
        mgr.commission_manager.claim_katheryne_reward()
        mgr.log_manager.update_quest(
            QuestEntry("q1", "Archon", QuestCategory.ARCHON,
                       status=QuestStatus.ACTIVE, is_tracked=True))
        action = mgr.get_next_action(25)
        assert action["action"] == "continue_quest"

    def test_no_quests_explore(self) -> None:
        mgr = QuestUIManager()
        action = mgr.get_next_action(25)
        assert action["action"] == "explore"


# ===================================================================
# Hangout Event tests
# ===================================================================

class TestHangoutHandler:
    def test_inactive_returns_wait(self):
        handler = HangoutHandler()
        state = HangoutState(is_active=False)
        decision = handler.evaluate(state)
        assert decision.action == "wait"

    def test_all_endings_unlocked(self):
        handler = HangoutHandler()
        state = HangoutState(
            is_active=True,
            endings_unlocked=["ending_1", "ending_2", "ending_3", "ending_4", "ending_5"],
            endings_total=5,
        )
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert "all_endings" in decision.reason

    def test_branch_selection_targets_unexplored(self):
        handler = HangoutHandler()
        state = HangoutState(
            is_active=True,
            endings_unlocked=["ending_1"],
            endings_total=3,
            current_branch_options=[
                HangoutBranch("b1", "Option A", leads_to_ending="ending_1"),
                HangoutBranch("b2", "Option B", leads_to_ending="ending_2"),
                HangoutBranch("b3", "Option C", leads_to_ending="ending_3"),
            ],
        )
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert "b2" in decision.reason  # First unexplored

    def test_all_explored_picks_first(self):
        handler = HangoutHandler()
        state = HangoutState(
            is_active=True,
            endings_unlocked=["ending_1", "ending_2"],
            endings_total=3,  # Not all unlocked yet
            current_branch_options=[
                HangoutBranch("b1", "Option A", leads_to_ending="ending_1"),
                HangoutBranch("b2", "Option B", leads_to_ending="ending_2"),
            ],
        )
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert "default" in decision.reason

    def test_record_ending(self):
        handler = HangoutHandler()
        state = HangoutState(is_active=True)
        state = handler.record_ending(state, "ending_1")
        assert "ending_1" in state.endings_unlocked
        # No duplicate
        state = handler.record_ending(state, "ending_1")
        assert state.endings_unlocked.count("ending_1") == 1

    def test_set_branch_options(self):
        handler = HangoutHandler()
        state = HangoutState(is_active=True)
        branches = [HangoutBranch("b1", "Go left"), HangoutBranch("b2", "Go right")]
        state = handler.set_branch_options(state, branches)
        assert len(state.current_branch_options) == 2

    def test_heart_event_checkpoint(self):
        handler = HangoutHandler()
        state = HangoutState(is_active=True, affection_checkpoint_met=True)
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert "heart" in decision.reason

    def test_no_branch_advances_dialog(self):
        handler = HangoutHandler()
        state = HangoutState(is_active=True)
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert "dialog" in decision.reason


class TestHangoutRouterIntegration:
    def test_router_routes_hangout(self):
        router = QuestMechanismRouter()
        decision = router.route(QuestMechanismType.HANGOUT)
        assert decision.action == "wait"  # Default inactive

    def test_identify_hangout_from_tags(self):
        router = QuestMechanismRouter()
        result = router.identify_mechanism({"tags": ["hangout"]})
        assert result == QuestMechanismType.HANGOUT

    def test_identify_hangout_from_type(self):
        router = QuestMechanismRouter()
        result = router.identify_mechanism({"type": "hangout"})
        assert result == QuestMechanismType.HANGOUT


# ===================================================================
# Event Quest tests
# ===================================================================

class TestEventQuestHandler:
    def test_inactive_returns_wait(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=False)
        decision = handler.evaluate(state)
        assert decision.action == "wait"

    def test_expired_event(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=True, days_remaining=0)
        decision = handler.evaluate(state)
        assert "expired" in decision.reason

    def test_intro_phase_drives_dialog(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=True, phase="intro")
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert decision.params.get("drive_dialog") is True

    def test_main_phase_plays_mini_game(self):
        handler = EventQuestHandler()
        state = EventQuestState(
            is_active=True, phase="main",
            currency_collected=200, currency_target=1000,
        )
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert "mini_game" in decision.reason

    def test_currency_target_met_advances(self):
        handler = EventQuestHandler()
        state = EventQuestState(
            is_active=True, phase="main",
            currency_collected=1000, currency_target=1000,
        )
        decision = handler.evaluate(state)
        assert "target_met" in decision.reason

    def test_challenge_phase_fights(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=True, phase="challenge")
        decision = handler.evaluate(state)
        assert decision.action == "fight"

    def test_finale_phase_drives_dialog(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=True, phase="finale")
        decision = handler.evaluate(state)
        assert decision.action == "proceed"
        assert decision.params.get("drive_dialog") is True

    def test_update_progress_currency(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=True, phase="main")
        state = handler.update_progress(state, currency_gained=100)
        assert state.currency_collected == 100

    def test_update_progress_mini_game(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=True, phase="main")
        state = handler.update_progress(state, mini_game_won=True)
        assert state.mini_games_completed == 1

    def test_update_progress_phase_transition(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=True, phase="intro")
        state = handler.update_progress(state, phase_complete=True)
        assert state.phase == "main"

    def test_phase_transitions_complete(self):
        handler = EventQuestHandler()
        state = EventQuestState(is_active=True, phase="main")
        state = handler.update_progress(state, phase_complete=True)
        assert state.phase == "challenge"
        state = handler.update_progress(state, phase_complete=True)
        assert state.phase == "finale"


class TestEventRouterIntegration:
    def test_router_routes_event(self):
        router = QuestMechanismRouter()
        decision = router.route(QuestMechanismType.EVENT)
        assert decision.action == "wait"  # Default inactive

    def test_identify_event_from_tags(self):
        router = QuestMechanismRouter()
        result = router.identify_mechanism({"tags": ["event"]})
        assert result == QuestMechanismType.EVENT

    def test_identify_event_from_type(self):
        router = QuestMechanismRouter()
        result = router.identify_mechanism({"type": "event"})
        assert result == QuestMechanismType.EVENT

    def test_router_gets_hangout_state(self):
        router = QuestMechanismRouter()
        state = router.get_state(QuestMechanismType.HANGOUT)
        assert isinstance(state, HangoutState)

    def test_router_gets_event_state(self):
        router = QuestMechanismRouter()
        state = router.get_state(QuestMechanismType.EVENT)
        assert isinstance(state, EventQuestState)

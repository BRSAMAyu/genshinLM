"""Tests for the flanking system (C-07)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from combat.flanking_policy import (
    FlankingContext,
    FlankingNavigator,
    FlankingPolicy,
    FlankingState,
    FlankingIntegration,
    FlankingAction,
    PositionStrategy,
)


# ---------------------------------------------------------------------------
# FlankingPolicy
# ---------------------------------------------------------------------------

class TestFlankingPolicy:

    def test_shield_wood_requires_flank(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_name="Mitachurl",
            enemy_type="mitachurl_wood",
            has_shield=True,
            shield_element="Wood",
            shield_broken=False,
        )
        assert policy.is_flanking_required(ctx) is True

    def test_shield_broken_no_flank(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_name="Mitachurl",
            enemy_type="mitachurl_wood",
            has_shield=True,
            shield_element="Wood",
            shield_broken=True,  # Shield broken — flanking not required
        )
        assert policy.is_flanking_required(ctx) is False

    def test_ice_shield_requires_flank(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_type="mitachurl_ice",
            has_shield=True,
            shield_element="Cryo",
            shield_broken=False,
        )
        assert policy.is_flanking_required(ctx) is True

    def test_no_shield_no_flank(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_type="slime",
            has_shield=False,
        )
        assert policy.is_flanking_required(ctx) is False

    def test_boss_dvalin_requires_flank(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_name="Dvalin",
            is_boss=True,
            has_shield=False,
        )
        assert policy.is_flanking_required(ctx) is True

    # Strategy decisions

    def test_stun_window_returns_phase_burst(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_type="slime",
            has_shield=False,
            in_stun_window=True,
            stun_window_remaining_sec=3.0,
        )
        state = FlankingState()
        strategy = policy.decide(ctx, state)
        assert strategy == PositionStrategy.PHASE_BURST

    def test_wood_shield_returns_flank_rear(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_type="mitachurl_wood",
            has_shield=True,
            shield_element="Wood",
            shield_broken=False,
            front_blocked=True,
        )
        state = FlankingState()
        strategy = policy.decide(ctx, state)
        assert strategy == PositionStrategy.FLANK_REAR

    def test_ice_shield_returns_flank_left(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_type="mitachurl_ice",
            has_shield=True,
            shield_element="Cryo",
            shield_broken=False,
        )
        state = FlankingState()
        strategy = policy.decide(ctx, state)
        assert strategy == PositionStrategy.FLANK_LEFT

    def test_boss_stunned_returns_phase_burst(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_name="Dvalin",
            is_boss=True,
            boss_phase="stunned",
            has_shield=False,
        )
        state = FlankingState()
        strategy = policy.decide(ctx, state)
        assert strategy == PositionStrategy.PHASE_BURST

    def test_boss_dvalin_returns_stalk_rear(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_name="Dvalin",
            is_boss=True,
            boss_phase="normal",
            has_shield=False,
        )
        state = FlankingState()
        strategy = policy.decide(ctx, state)
        assert strategy == PositionStrategy.STALK_REAR

    def test_staggered_returns_phase_burst(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_type="hilichurl",
            has_shield=False,
            is_staggered=True,
        )
        state = FlankingState()
        strategy = policy.decide(ctx, state)
        assert strategy == PositionStrategy.PHASE_BURST

    def test_default_returns_kite_around(self) -> None:
        policy = FlankingPolicy()
        ctx = FlankingContext(
            enemy_type="hilichurl",
            has_shield=False,
        )
        state = FlankingState()
        strategy = policy.decide(ctx, state)
        assert strategy == PositionStrategy.KITE_AROUND


# ---------------------------------------------------------------------------
# FlankingNavigator
# ---------------------------------------------------------------------------

class TestFlankingNavigator:

    def test_compute_action_flank_rear(self) -> None:
        nav = FlankingNavigator()
        ctx = FlankingContext(enemy_name="Mitachurl", enemy_type="mitachurl_wood")
        action = nav.compute_action(PositionStrategy.FLANK_REAR, ctx)
        assert action.action_type == "move_back_then_circles_left"
        assert action.urgency == 0.9
        assert action.target_strategy == PositionStrategy.FLANK_REAR

    def test_compute_action_stalk_rear(self) -> None:
        nav = FlankingNavigator()
        ctx = FlankingContext(enemy_name="Dvalin", is_boss=True)
        action = nav.compute_action(PositionStrategy.STALK_REAR, ctx)
        assert action.action_type == "adjust_to_rear"
        assert action.urgency == 0.5

    def test_compute_action_phase_burst(self) -> None:
        nav = FlankingNavigator()
        ctx = FlankingContext(stun_window_remaining_sec=4.0)
        action = nav.compute_action(PositionStrategy.PHASE_BURST, ctx)
        assert action.action_type == "sprint_to_rear"
        assert action.urgency == 1.0

    def test_compute_action_flank_left(self) -> None:
        nav = FlankingNavigator()
        action = nav.compute_action(PositionStrategy.FLANK_LEFT, FlankingContext())
        assert action.action_type == "circles_left"
        assert action.reason == "circle left around "

    def test_compute_action_aggressive_front(self) -> None:
        nav = FlankingNavigator()
        action = nav.compute_action(PositionStrategy.AGGRESSIVE_FRONT, FlankingContext())
        assert action.action_type == "advance"

    def test_execute_action_calls_backend(self) -> None:
        mock_backend = MagicMock()
        nav = FlankingNavigator()
        action = FlankingAction(
            action_type="circles_left",
            urgency=0.7,
            target_strategy=PositionStrategy.FLANK_LEFT,
        )
        ok = nav.execute_action(action, mock_backend)
        assert ok is True
        mock_backend.key_press.assert_called_once_with("A", reason="flank_circle_left")

    def test_execute_action_sprint_to_rear(self) -> None:
        mock_backend = MagicMock()
        nav = FlankingNavigator()
        action = FlankingAction(
            action_type="sprint_to_rear",
            urgency=1.0,
            target_strategy=PositionStrategy.PHASE_BURST,
        )
        ok = nav.execute_action(action, mock_backend)
        assert ok is True
        mock_backend.key_down.assert_called_once()
        mock_backend.key_press.assert_called_once()
        mock_backend.key_up.assert_called_once()

    def test_execute_action_no_backend(self) -> None:
        nav = FlankingNavigator()
        action = FlankingAction(action_type="advance", urgency=0.3)
        ok = nav.execute_action(action, None)
        assert ok is False

    def test_update_state_strategy_change(self) -> None:
        state = FlankingState(current_strategy=PositionStrategy.AGGRESSIVE_FRONT)
        nav = FlankingNavigator()
        nav.update_state(PositionStrategy.FLANK_REAR, state)
        assert state.current_strategy == PositionStrategy.FLANK_REAR
        assert state.strategy_streak == 0

    def test_update_state_strategy_unchanged(self) -> None:
        state = FlankingState(current_strategy=PositionStrategy.FLANK_REAR, strategy_streak=2)
        nav = FlankingNavigator()
        nav.update_state(PositionStrategy.FLANK_REAR, state)
        assert state.strategy_streak == 3

    def test_build_flanking_context(self) -> None:
        nav = FlankingNavigator()
        ctx = nav.build_flanking_context(
            enemy_name="Mitachurl",
            enemy_type="mitachurl_wood",
            shield_element="Wood",
            shield_broken=False,
            is_boss=False,
        )
        assert ctx.enemy_name == "Mitachurl"
        assert ctx.has_shield is True
        assert ctx.shield_broken is False
        assert ctx.in_stun_window is False


# ---------------------------------------------------------------------------
# FlankingIntegration
# ---------------------------------------------------------------------------

class TestFlankingIntegration:

    def test_high_urgency_executes(self) -> None:
        mock_backend = MagicMock()
        integration = FlankingIntegration(backend=mock_backend)

        ctx = FlankingContext(
            enemy_type="mitachurl_wood",
            has_shield=True,
            shield_element="Wood",
            shield_broken=False,
            front_blocked=True,
        )
        executed, strategy = integration.evaluate_and_execute(ctx)
        assert executed is True
        assert strategy == "flank_rear"

    def test_low_urgency_no_execute(self) -> None:
        mock_backend = MagicMock()
        integration = FlankingIntegration(backend=mock_backend)

        ctx = FlankingContext(
            enemy_type="hilichurl",
            has_shield=False,
        )
        executed, strategy = integration.evaluate_and_execute(ctx)
        # Default is KITE_AROUND, urgency=0.4 < 0.7, so no action
        assert executed is False

    def test_stun_window_always_executes(self) -> None:
        mock_backend = MagicMock()
        integration = FlankingIntegration(backend=mock_backend)

        ctx = FlankingContext(
            enemy_type="slime",
            has_shield=False,
            in_stun_window=True,
            stun_window_remaining_sec=3.0,
        )
        executed, strategy = integration.evaluate_and_execute(ctx)
        assert executed is True
        assert strategy == "phase_burst"

    def test_get_current_strategy(self) -> None:
        mock_backend = MagicMock()
        integration = FlankingIntegration(backend=mock_backend)
        assert integration.get_current_strategy() == "aggressive_front"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""Unit tests for the Sparkle Agent Kernel Minimal Closed-Loop pipeline."""
from __future__ import annotations

import pytest

from agent_kernel.minimal_closed_loop import SparkleClosedLoopRunner
from agent_kernel.types import GoalResult


def test_minimal_closed_loop_execution():
    """Verify that the full closed-loop pipeline executes and adjudicates successfully."""
    runner = SparkleClosedLoopRunner()
    
    # 1. Run the entire pipeline simulation
    command = "The option 'Daily Commissions' has a low confidence because of flower petals, lower threshold to 0.2 and click it"
    result = runner.run_pipeline(command)
    
    # 2. Assert structural correctness of the final GoalResult
    assert isinstance(result, GoalResult)
    assert result.achieved is True
    assert result.steps_total == 1
    assert result.steps_succeeded == 1
    assert len(result.verified_claims) == 1
    
    # 3. Assert claim values
    claim = result.verified_claims[0]
    assert claim.verified is True
    assert claim.confidence >= 0.95
    assert "daily_commission_click_verify" in claim.attributions

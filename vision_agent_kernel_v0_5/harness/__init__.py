"""Trial-and-error harness (ROADMAP Phase 1).

The autonomous-iteration engine: run a policy in an environment over many
scenarios, score pass/fail, capture replayable traces, cluster failures, and
aggregate a batch report. Game-agnostic and offline-first — environments are
pluggable (a deterministic simulator now, a real-game adapter later).

This is the substrate that turns "the agent learns by trial and error" from a
slogan into a measurable, parallelizable loop.
"""
from __future__ import annotations

from harness.core import (
    FailureCluster,
    Scenario,
    ScenarioResult,
    StepRecord,
)

__all__ = [
    "Scenario",
    "StepRecord",
    "ScenarioResult",
    "FailureCluster",
]

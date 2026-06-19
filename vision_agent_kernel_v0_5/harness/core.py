"""Core types and protocols for the trial-and-error harness."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Scenario:
    """A declarative test situation: a starting condition + an objective.

    ``setup`` is environment-specific (e.g. start/target coords, seed, obstacles).
    The harness stays game-agnostic; the environment interprets ``setup``.
    """

    scenario_id: str
    objective: str
    setup: JsonDict = field(default_factory=dict)
    max_steps: int = 500
    timeout_sec: float = 60.0
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StepRecord:
    """One step of a run, serializable for replay."""

    step: int
    observation: JsonDict
    action: JsonDict
    info: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Outcome of running one scenario."""

    scenario_id: str
    passed: bool
    score: float
    steps: int
    failure_code: str | None
    reason: str
    metrics: JsonDict = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    trace_ref: str = ""


@dataclass(frozen=True, slots=True)
class FailureCluster:
    """A group of failures sharing a signature, for targeted fixing."""

    signature: str
    count: int
    scenario_ids: tuple[str, ...]
    example_reason: str


@dataclass(frozen=True, slots=True)
class BatchReport:
    """Aggregate over a batch run, with optional regression vs a baseline."""

    total: int
    passed: int
    failed: int
    pass_rate: float
    clusters: tuple[FailureCluster, ...]
    results: tuple[ScenarioResult, ...]
    regressions: tuple[str, ...] = ()   # scenario_ids that passed in baseline but fail now
    fixed: tuple[str, ...] = ()         # scenario_ids that failed in baseline but pass now


class Environment(Protocol):
    """A resettable, steppable world. ``info`` carries done-cause + metrics."""

    def reset(self, scenario: Scenario) -> JsonDict:
        """Return the initial observation."""
        ...

    def step(self, action: JsonDict) -> tuple[JsonDict, bool, JsonDict]:
        """Apply ``action``; return (observation, done, info)."""
        ...


class Policy(Protocol):
    """The thing under test. Maps observations to actions."""

    def reset(self, scenario: Scenario) -> None:
        ...

    def act(self, observation: JsonDict) -> JsonDict:
        ...


class Scorer(Protocol):
    """Turns a finished run into a :class:`ScenarioResult`."""

    def score(
        self,
        scenario: Scenario,
        trace: list[StepRecord],
        last_info: JsonDict,
        done: bool,
        steps: int,
    ) -> ScenarioResult:
        ...

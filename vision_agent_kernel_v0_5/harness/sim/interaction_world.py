"""Deterministic interaction world — Phase 3 dogfood environment.

Models a scripted dialogue/quest interaction the controller must traverse:
interact-prompts, multi-line dialogue, branching choices (one correct branch),
and a final reward to claim. A wrong choice dead-ends the interaction (failure),
so the controller's goal-aligned choice logic is what's under test.
"""
from __future__ import annotations

import random

from harness.core import JsonDict, Scenario
from interaction.interaction_controller import (
    InteractionAction,
    InteractionController,
    InteractionView,
)


class InteractionEnv:
    """Implements the harness Environment protocol for scripted interactions."""

    def __init__(self) -> None:
        self._script: list[JsonDict] = []
        self._pos = 0

    def reset(self, scenario: Scenario) -> JsonDict:
        self._script = list(scenario.setup["script"])
        self._pos = 0
        return self._observe()

    def step(self, action: JsonDict) -> tuple[JsonDict, bool, JsonDict]:
        node = self._script[self._pos]
        kind = node["kind"]
        act = action.get("kind", "idle")
        advanced = False
        failed = False

        if kind == "prompt":
            if act in ("interact", "confirm"):
                advanced = True
        elif kind == "dialogue":
            if act == "advance":
                advanced = True
        elif kind == "choice":
            if act == "choose":
                if int(action.get("choice_index", -1)) == int(node["correct"]):
                    advanced = True
                else:
                    failed = True  # wrong branch dead-ends
        elif kind == "reward":
            if act == "claim":
                advanced = True

        if advanced:
            self._pos += 1

        success = self._pos >= len(self._script)
        done = success or failed
        failure_code = None if not failed else "wrong_choice"
        info: JsonDict = {
            "success": success,
            "failure_code": failure_code,
            "reason": "interaction complete" if success else (failure_code or "in_progress"),
            "progress": self._pos / max(len(self._script), 1),
        }
        return self._observe(), done, info

    def _observe(self) -> JsonDict:
        if self._pos >= len(self._script):
            return {"screen": "none", "dialogue_active": False, "choices": [],
                    "prompt": "", "reward_ready": False, "objective_hint": ""}
        node = self._script[self._pos]
        kind = node["kind"]
        return {
            "screen": kind,
            "dialogue_active": kind == "dialogue",
            "choices": list(node.get("choices", [])),
            "prompt": node.get("prompt", "") if kind == "prompt" else "",
            "reward_ready": kind == "reward",
            "objective_hint": node.get("goal", ""),
        }


class InteractionPolicy:
    """Drives the real InteractionController from InteractionEnv observations."""

    def __init__(self, controller: InteractionController | None = None) -> None:
        self._controller = controller or InteractionController()

    def reset(self, scenario: Scenario) -> None:
        pass

    def act(self, obs: JsonDict) -> JsonDict:
        view = InteractionView(
            screen=obs.get("screen", "none"),
            dialogue_active=obs.get("dialogue_active", False),
            choices=tuple(obs.get("choices", ())),
            prompt=obs.get("prompt", ""),
            reward_ready=obs.get("reward_ready", False),
            objective_hint=obs.get("objective_hint", ""),
        )
        action: InteractionAction = self._controller.decide(view)
        return {"kind": action.kind, "choice_index": action.choice_index}


def make_interaction_scenarios(n: int, *, seed: int = 0) -> list[Scenario]:
    """Generate deterministic dialogue/quest interaction scripts."""
    rng = random.Random(seed)
    topics = [
        ("accept the commission", ["Accept the commission", "Decline"]),
        ("ask about the ruins", ["Ask about the ruins", "Say goodbye"]),
        ("help with the search", ["Help with the search", "Not now"]),
        ("turn in the report", ["Turn in the report", "Leave"]),
    ]
    scenarios: list[Scenario] = []
    for i in range(n):
        script: list[JsonDict] = [{"kind": "prompt", "prompt": "Talk to NPC", "goal": "talk"}]
        for _ in range(rng.randint(1, 3)):
            script.append({"kind": "dialogue", "goal": "advance"})
        goal, choices = rng.choice(topics)
        # correct = the goal-aligned option (index 0 in our topic pairs)
        order = [0, 1]
        rng.shuffle(order)
        shuffled = [choices[o] for o in order]
        correct = order.index(0)
        script.append({"kind": "choice", "goal": goal, "choices": shuffled, "correct": correct})
        for _ in range(rng.randint(0, 2)):
            script.append({"kind": "dialogue", "goal": "advance"})
        script.append({"kind": "reward", "goal": "claim reward"})
        scenarios.append(Scenario(
            scenario_id=f"intr-{seed}-{i:03d}", objective=goal,
            setup={"script": script}, max_steps=40, tags=("interaction",),
        ))
    return scenarios

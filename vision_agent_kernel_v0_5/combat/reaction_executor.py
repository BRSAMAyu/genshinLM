from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from combat.character_switch_manager import CharacterSwitchManager

log = logging.getLogger(__name__)


def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
    import time
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))


@dataclass(frozen=True, slots=True)
class ReactionStep:
    element: str
    action: str  # "use_skill" or "use_burst"


_REACTION_SEQUENCES: dict[str, list[ReactionStep]] = {
    "vaporize": [
        ReactionStep("hydro", "use_skill"),
        ReactionStep("pyro", "use_burst"),
    ],
    "melt": [
        ReactionStep("cryo", "use_skill"),
        ReactionStep("pyro", "use_burst"),
    ],
    "overloaded": [
        ReactionStep("electro", "use_skill"),
        ReactionStep("pyro", "use_skill"),
    ],
    "hyperbloom": [
        ReactionStep("dendro", "use_skill"),
        ReactionStep("hydro", "use_skill"),
        ReactionStep("electro", "use_burst"),
    ],
    "freeze": [
        ReactionStep("hydro", "use_skill"),
        ReactionStep("cryo", "use_burst"),
    ],
    "superconduct": [
        ReactionStep("electro", "use_skill"),
        ReactionStep("cryo", "use_skill"),
    ],
    "electro_charged": [
        ReactionStep("hydro", "use_skill"),
        ReactionStep("electro", "use_skill"),
    ],
    "swirl_pyro": [
        ReactionStep("pyro", "use_skill"),
        ReactionStep("anemo", "use_burst"),
    ],
}


class ReactionExecutor:
    """Execute specific elemental reaction sequences."""

    def __init__(self, switch_manager: CharacterSwitchManager) -> None:
        self._switch = switch_manager

    def execute_reaction(
        self,
        reaction_name: str,
        team_elements: list[str],
        team_slots: list[int] | None = None,
    ) -> bool:
        """Execute the named reaction sequence. Returns True if all steps executed."""
        steps = _REACTION_SEQUENCES.get(reaction_name)
        if steps is None:
            log.warning("[ReactionExecutor] unknown reaction: %s", reaction_name)
            return False
        if team_slots is None:
            team_slots = [1, 2, 3, 4]
        element_to_slot: dict[str, int] = {}
        for elem, slot in zip(team_elements, team_slots):
            element_to_slot.setdefault(elem, slot)

        for step in steps:
            slot = element_to_slot.get(step.element)
            if slot is None:
                log.warning(
                    "[ReactionExecutor] no %s character for %s", step.element, reaction_name
                )
                return False
            if not self._switch.switch_to(slot, reason=f"reaction_{reaction_name}"):
                return False
            _chunked_sleep(0.3)
        log.info("[ReactionExecutor] executed %s sequence", reaction_name)
        return True

    @staticmethod
    def available_reactions(team_elements: list[str]) -> list[str]:
        """List reactions possible with given team elements."""
        elem_set = set(team_elements)
        available: list[str] = []
        for name, steps in _REACTION_SEQUENCES.items():
            required = {s.element for s in steps}
            if required <= elem_set:
                available.append(name)
        return available

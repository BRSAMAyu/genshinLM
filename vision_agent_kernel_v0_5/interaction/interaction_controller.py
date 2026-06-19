"""Game-agnostic interaction controller (ROADMAP Phase 3).

A reference decision policy for dialogue / prompts / choices / reward screens. It
advances conversations, picks the choice that best serves the current objective,
confirms interact prompts, and claims rewards — without any game-specific pixel
logic. A capsule feeds a real :class:`InteractionView` from perception/OCR; the
sim feeds a simulated one. The decision priority is the testable contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Words that signal the "progress / opt-in" branch when no goal keyword matches.
_POSITIVE = (
    "accept", "yes", "ok", "okay", "continue", "confirm", "claim", "sure",
    "help", "agree", "start", "begin", "next", "proceed", "talk",
)
_NEGATIVE = ("decline", "no", "leave", "cancel", "later", "refuse", "back", "exit")


@dataclass(frozen=True, slots=True)
class InteractionView:
    screen: str = "none"            # dialogue | choice | prompt | reward | none
    dialogue_active: bool = False
    choices: tuple[str, ...] = ()
    prompt: str = ""                # interact-prompt text, if any
    reward_ready: bool = False
    objective_hint: str = ""        # what we're trying to accomplish


@dataclass(frozen=True, slots=True)
class InteractionAction:
    kind: str  # advance | choose | confirm | claim | interact | idle
    choice_index: int = -1
    reason: str = ""


@dataclass(frozen=True, slots=True)
class InteractionConfig:
    avoid_negative: bool = True  # never pick a clearly-negative option as fallback


class InteractionController:
    def __init__(self, config: InteractionConfig | None = None) -> None:
        self._cfg = config or InteractionConfig()

    def decide(self, view: InteractionView) -> InteractionAction:
        # 1. Claim any reward on offer.
        if view.reward_ready or view.screen == "reward":
            return InteractionAction("claim", reason="claim reward")

        # 2. Make a choice — the goal-aligned branch.
        if view.choices:
            idx = self._best_choice(view.choices, view.objective_hint)
            return InteractionAction("choose", choice_index=idx, reason="select option")

        # 3. Advance dialogue.
        if view.dialogue_active or view.screen == "dialogue":
            return InteractionAction("advance", reason="advance dialogue")

        # 4. Confirm / trigger an interact prompt.
        if view.screen == "prompt" or view.prompt:
            return InteractionAction("interact", reason="interact / confirm prompt")

        return InteractionAction("idle", reason="nothing to do")

    def _best_choice(self, choices: tuple[str, ...], goal: str) -> int:
        goal_tokens = {t for t in _tokenize(goal) if len(t) > 2}

        # Best overlap with the objective keywords.
        best_idx, best_score = -1, 0
        for i, choice in enumerate(choices):
            score = len(goal_tokens & set(_tokenize(choice)))
            if score > best_score:
                best_idx, best_score = i, score
        if best_idx >= 0:
            return best_idx

        # Fallback: first clearly-positive option.
        for i, choice in enumerate(choices):
            low = choice.lower()
            if any(p in low for p in _POSITIVE):
                return i

        # Last resort: first non-negative, else first.
        if self._cfg.avoid_negative:
            for i, choice in enumerate(choices):
                if not any(nw in choice.lower() for nw in _NEGATIVE):
                    return i
        return 0


def _tokenize(text: str) -> list[str]:
    return [t for t in "".join(c if c.isalnum() else " " for c in text.lower()).split()]

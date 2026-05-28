"""EpisodeSegmenter — split trace sessions into coherent episodes.

An episode is a subsequence of actions within a session that forms a
logical unit (same screen state, continuous timing, coherent goal).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from learning.skill_induction.trace_recorder import RecordedAction, TraceSession


@dataclass(frozen=True, slots=True)
class Episode:
    """A coherent subsequence of actions."""
    episode_id: str
    goal: str
    screen_state: str
    actions: tuple[RecordedAction, ...]
    viewport: tuple[int, int] = (1920, 1080)

    @property
    def has_anchors(self) -> bool:
        return any(a.anchor_id for a in self.actions)

    @property
    def duration_sec(self) -> float:
        if not self.actions:
            return 0.0
        return self.actions[-1].timestamp - self.actions[0].timestamp


class EpisodeSegmenter:
    """Segments trace sessions into episodes by screen state transitions."""

    def segment(self, session: TraceSession) -> list[Episode]:
        """Split session into episodes at screen state boundaries."""
        if not session.actions:
            return []

        episodes: list[Episode] = []
        current_actions: list[RecordedAction] = [session.actions[0]]
        current_state = session.actions[0].screen_state or session.screen_state or "unknown"
        ep_idx = 0

        for action in session.actions[1:]:
            action_state = action.screen_state or current_state
            if action_state != current_state and action_state:
                episodes.append(self._make_episode(
                    ep_idx, session.goal, current_state, current_actions, session.viewport,
                ))
                ep_idx += 1
                current_actions = [action]
                current_state = action_state
            else:
                current_actions.append(action)

        if current_actions:
            episodes.append(self._make_episode(
                ep_idx, session.goal, current_state, current_actions, session.viewport,
            ))

        return episodes

    def _make_episode(
        self,
        idx: int,
        goal: str,
        screen_state: str,
        actions: list[RecordedAction],
        viewport: tuple[int, int],
    ) -> Episode:
        return Episode(
            episode_id=f"ep_{idx}_{goal[:12]}",
            goal=goal,
            screen_state=screen_state,
            actions=tuple(actions),
            viewport=viewport,
        )

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from core.types import FocusState, Observation, TargetTrack
from execution.verifier_base import VerifierContext


@dataclass(slots=True)
class RealisticScenarioState:
    target_hp_ratio: float = 1.0
    target_visible: bool = True
    collectable_visible: bool = True
    interaction_prompt_visible: bool = False
    gain_popup: bool = False
    target_lost_ticks: int = 0
    completed_nodes: list[str] = field(default_factory=list)


class RealisticTestbed:
    width: int = 1280
    height: int = 720

    def __init__(self) -> None:
        self.state = RealisticScenarioState()
        self.frame_id = 0

    def frame(self) -> np.ndarray:
        self.frame_id += 1
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._draw_hp(frame)
        if self.state.target_visible and self.state.target_hp_ratio > 0.0:
            frame[300:360, 610:670, 0] = 220
        if self.state.collectable_visible:
            frame[340:380, 620:660, 1] = 220
        if self.state.interaction_prompt_visible:
            frame[500:535, 560:720, :] = 180
        return frame

    def _draw_hp(self, frame: np.ndarray) -> None:
        frame[24:38, 80:380, :] = 40
        hp_width = int(300 * max(0.0, min(1.0, self.state.target_hp_ratio)))
        if hp_width > 0:
            frame[24:38, 80 : 80 + hp_width, 0] = 230
            frame[24:38, 80 : 80 + hp_width, 1] = 20
            frame[24:38, 80 : 80 + hp_width, 2] = 20

    def observation(self) -> Observation:
        track = None
        if self.state.target_visible and self.state.target_hp_ratio > 0.0:
            track = TargetTrack(
                track_id="monster_a",
                class_id="monster",
                state="TRACKED",
                bbox_xyxy=(610, 300, 670, 360),
                smoothed_center_px=(640, 330),
                velocity_px_s=(0.0, 0.0),
                confidence=0.9,
                identity_confidence=0.9,
                missing_duration_ms=0.0,
                bearing_deg=0.0,
                pitch_deg=0.0,
                estimated_range=10.0,
                last_seen_frame_id=self.frame_id,
            )
        return Observation(
            frame_id=self.frame_id,
            t_capture=time.perf_counter(),
            t_processed=time.perf_counter(),
            latency_ms=1.0,
            viewport_size=(self.width, self.height),
            target_track=track,
            obstacle_field=None,
            ui_state=None,
            visual_triggers={
                "interaction_prompt_visible": self.state.interaction_prompt_visible,
                "gain_popup": self.state.gain_popup,
                "target_visible": self.state.target_visible,
            },
            os_focus=FocusState(True, "pseudo3d_scene"),
        )

    def context(self, extra: dict | None = None) -> VerifierContext:
        state = {
            "target_hp_ratio": self.state.target_hp_ratio,
            "target_defeated": self.state.target_hp_ratio <= 0.0,
            "target_visible": self.state.target_visible,
            "collection_started": True,
            "item_disappeared": not self.state.collectable_visible,
            "interaction_prompt_visible": self.state.interaction_prompt_visible,
            "gain_popup": self.state.gain_popup,
            **(extra or {}),
        }
        obs = self.observation()
        return VerifierContext(state=state, observation=obs, frame=self.frame(), ocr_text="Collect" if self.state.interaction_prompt_visible else "", target_track=obs.target_track)

    def attack(self) -> None:
        self.state.target_hp_ratio = max(0.0, self.state.target_hp_ratio - 0.5)
        if self.state.target_hp_ratio <= 0.0:
            self.state.target_visible = False
            self.state.completed_nodes.append("combat")

    def collect(self) -> None:
        if self.state.interaction_prompt_visible:
            self.state.collectable_visible = False
            self.state.gain_popup = True
            self.state.completed_nodes.append("collection")

    def approach_collectable(self) -> None:
        self.state.interaction_prompt_visible = True

    def lose_target(self) -> None:
        self.state.target_visible = False
        self.state.target_lost_ticks += 1

    def reacquire(self) -> None:
        self.state.target_visible = True
        self.state.target_lost_ticks = 0

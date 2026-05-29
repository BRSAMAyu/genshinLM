"""Genshin Impact autonomous game agent.

Connects the kernel pipeline to AutonomousTaskBrain for real Genshin gameplay.
Uses dxcam for capture, Zhipu GLM-4V for VLM, GenshinScreenClassifier for
screen state, and SafeWindowInputBackend for input.

Usage:
    python scripts/run_genshin_agent.py --goal "完成主线任务" --window-title "原神"
"""
from __future__ import annotations

import io
import json
import logging
import time
from typing import Any

import numpy as np

from agent.autonomous_task_brain import AutonomousTaskBrain, ActionExecutor, PerceptionProvider, TaskBrainConfig
from core.local_secret_store import get_secret
from core.state_bus import StateBus
from core.timebase import Timebase
from execution.safe_window_backend import SafeWindowInputBackend
from planning.screen_state_claim_builder import ClassifierOutput, OcrOutput, VLMOutput

log = logging.getLogger(__name__)


def _encode_frame_jpeg(frame: np.ndarray, max_long_side: int = 1280) -> bytes:
    """Encode frame as JPEG, resizing if needed."""
    try:
        import cv2
        h, w = frame.shape[:2]
        if max(h, w) > max_long_side:
            scale = max_long_side / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        success, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if success:
            return encoded.tobytes()
    except ImportError:
        pass
    from PIL import Image
    h, w = frame.shape[:2]
    if max(h, w) > max_long_side:
        scale = max_long_side / max(h, w)
        frame = frame.copy()
        # Simple resize via slicing — crude but works without cv2
    rgb = frame[:, :, ::-1] if frame.shape[-1] == 3 else frame
    img = Image.fromarray(rgb)
    if max(h, w) > max_long_side:
        scale = max_long_side / max(h, w)
        img = img.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class GenshinPerceptionProvider:
    """PerceptionProvider implementation using dxcam + Zhipu VLM + Genshin classifier."""

    def __init__(
        self,
        window_title: str,
        api_key: str | None = None,
    ) -> None:
        self._api_key = api_key or get_secret("ZHIPU_API_KEY") or ""
        self._timebase = Timebase()
        self._frame_id = 0

        # Screen capture
        from perception.dxcam_capture import DxcamCapturer, CaptureConfig
        self._capturer = DxcamCapturer(CaptureConfig(target_fps=15.0), timebase=self._timebase)

        # Screen classifier
        from perception.genshin_screen_classifier import GenshinScreenClassifier
        self._classifier = GenshinScreenClassifier()

        # VLM API
        self._vlm_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self._vlm_model = "glm-4v-flash"

    def start(self) -> None:
        self._capturer.start()
        log.info("[GenshinPerception] Started capture")

    def stop(self) -> None:
        self._capturer.stop()

    def capture_frame(self) -> np.ndarray | None:
        packet = self._capturer.get_latest_frame()
        if packet is None:
            return None
        self._frame_id = packet.frame_id
        return packet.image

    def analyze_vlm(self, frame: np.ndarray, game_id: str) -> VLMOutput | None:
        if not self._api_key:
            log.warning("[GenshinPerception] No API key for VLM")
            return None
        try:
            jpeg = _encode_frame_jpeg(frame, max_long_side=1280)
            import base64
            img_b64 = base64.b64encode(jpeg).decode("ascii")

            prompt = (
                'Analyze this Genshin Impact screenshot. Return strict JSON only:\n'
                '{\n'
                '  "screen_state": "loading_screen|dialog|world_hud|full_menu|paimon_menu|no_hud|combat",\n'
                '  "player_status": {"hp":"high/medium/low","stamina":"high/medium/low","location":"description"},\n'
                '  "visible_objects": [{"type":"monster|npc|item|chest|waypoint","description":"...","position":"center/left/right"}],\n'
                '  "ui_elements": {"element_id":"visible_text_or_label"},\n'
                '  "scene_description": "what is happening on screen",\n'
                '  "suggested_action": "what the player should do next"\n'
                '}'
            )

            import urllib.request
            payload = {
                "model": self._vlm_model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    ],
                }],
                "temperature": 0.1,
                "stream": False,
                "max_tokens": 800,
            }
            request = urllib.request.Request(
                self._vlm_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._extract_json(text)
            if parsed is None:
                return VLMOutput(
                    screen_state="unknown", player_status={},
                    visible_objects=[], ui_elements={},
                    scene_description=text, suggested_action="observe",
                    raw_text=text,
                )
            return VLMOutput(
                screen_state=parsed.get("screen_state", "unknown"),
                player_status=parsed.get("player_status", {}),
                visible_objects=parsed.get("visible_objects", []),
                ui_elements=parsed.get("ui_elements", {}),
                scene_description=parsed.get("scene_description", ""),
                suggested_action=parsed.get("suggested_action", "observe"),
                raw_text=text,
            )
        except Exception as exc:
            log.warning("[GenshinPerception] VLM analysis failed: %s", exc)
            return None

    def classify_screen(self, frame: np.ndarray) -> ClassifierOutput | None:
        result = self._classifier.classify(frame)
        return ClassifierOutput(
            screen_state=result.state,
            confidence=result.confidence,
            source="genshin_classifier",
        )

    def ocr_scan(self, frame: np.ndarray) -> list[OcrOutput]:
        # OCR is optional — return empty for now, can be wired later
        return []

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        # Strip markdown fences
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # Try to find JSON object in text
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass
        return None


class GenshinActionExecutor:
    """ActionExecutor implementation using SafeWindowInputBackend.

    Translates semantic actions (from HierarchicalPlanner) into concrete
    key/mouse inputs for Genshin Impact.
    """

    def __init__(self, backend: SafeWindowInputBackend) -> None:
        self._backend = backend
        self._timebase = Timebase()

    def execute_semantic(self, action: str, target: str, context: dict[str, Any]) -> bool:
        log.info("[GenshinExecutor] action=%s target=%s", action, target)
        try:
            handler = self._ACTION_MAP.get(action, self._handle_unknown)
            return handler(self, target, context)
        except Exception as exc:
            log.warning("[GenshinExecutor] Action %s failed: %s", action, exc)
            return False

    def is_target_focused(self) -> bool:
        return self._backend.is_target_focused()

    def _handle_move(self, target: str, context: dict[str, Any]) -> bool:
        direction = target.lower() if target else "forward"
        keys: list[str] = []
        if "forward" in direction:
            keys.append("w")
        elif "back" in direction:
            keys.append("s")
        else:
            keys.append("w")

        if "left" in direction:
            keys.append("a")
        elif "right" in direction:
            keys.append("d")

        # Single direction fallback
        if not keys:
            key_map = {"forward": "w", "back": "s", "left": "a", "right": "d"}
            keys = [key_map.get(direction, "w")]

        for key in keys:
            self._backend.key_down(key, reason=f"move_{key}")
        time.sleep(1.5)
        for key in keys:
            self._backend.key_up(key, reason=f"move_{key}_done")
        return True

    def _handle_navigate_to(self, target: str, context: dict[str, Any]) -> bool:
        # Open map with M, but navigation requires visual feedback not yet implemented
        self._press_key("m", "open_map", 0.5)
        time.sleep(1.0)
        log.warning("[GenshinExecutor] navigate_to is not yet fully implemented for target=%s", target)
        return False

    def _handle_open_menu(self, target: str, context: dict[str, Any]) -> bool:
        self._press_key("esc", "open_menu", 0.3)
        return True

    def _handle_close_menu(self, target: str, context: dict[str, Any]) -> bool:
        self._press_key("esc", "close_menu", 0.3)
        return True

    def _handle_advance_dialog(self, target: str, context: dict[str, Any]) -> bool:
        # Space to advance dialog
        self._press_key("space", "advance_dialog", 0.3)
        return True

    def _handle_select_option(self, target: str, context: dict[str, Any]) -> bool:
        if target and target.isdigit():
            self._press_key(target, f"select_option_{target}", 0.3)
        else:
            self._press_key("1", "select_first_option", 0.3)
        return True

    def _handle_use_skill(self, target: str, context: dict[str, Any]) -> bool:
        skill_map = {"e": "e", "q": "q", "1": "1", "2": "2", "3": "3", "4": "4"}
        key = skill_map.get(target, "e")
        self._press_key(key, f"use_skill_{key}", 0.3)
        return True

    def _handle_basic_attack(self, target: str, context: dict[str, Any]) -> bool:
        # Left click for basic attack — Genshin uses left mouse for normal attacks
        self._backend.left_click(reason="basic_attack")
        return True

    def _handle_observe(self, target: str, context: dict[str, Any]) -> bool:
        # Just wait and observe
        time.sleep(2.0)
        return True

    def _handle_go_back(self, target: str, context: dict[str, Any]) -> bool:
        self._press_key("esc", "go_back", 0.3)
        return True

    def _handle_confirm(self, target: str, context: dict[str, Any]) -> bool:
        self._press_key("enter", "confirm", 0.3)
        return True

    def _handle_interact(self, target: str, context: dict[str, Any]) -> bool:
        # F key for interaction (NPCs, chests, items)
        self._press_key("f", "interact", 0.3)
        return True

    def _handle_jump(self, target: str, context: dict[str, Any]) -> bool:
        self._press_key("space", "jump", 0.15)
        return True

    def _handle_dash(self, target: str, context: dict[str, Any]) -> bool:
        self._press_key("shift", "dash", 0.2)
        return True

    def _handle_sprint(self, target: str, context: dict[str, Any]) -> bool:
        self._backend.key_down("shift", reason="sprint_start")
        time.sleep(2.0)
        self._backend.key_up("shift", reason="sprint_end")
        return True

    def _handle_swim(self, target: str, context: dict[str, Any]) -> bool:
        self._backend.key_down("shift", reason="swim_dash")
        time.sleep(0.3)
        self._backend.key_up("shift", reason="swim_dash_end")
        return True

    def _handle_unknown(self, target: str, context: dict[str, Any]) -> bool:
        log.warning("[GenshinExecutor] Unknown action, treating as observe: %s", target)
        time.sleep(1.0)
        return True

    def _press_key(self, key: str, reason: str, hold_sec: float = 0.1) -> None:
        self._backend.key_down(key, reason=reason)
        time.sleep(hold_sec)
        self._backend.key_up(key, reason=f"{reason}_done")

    _ACTION_MAP: dict[str, Any] = {
        "move": _handle_move,
        "navigate_to": _handle_navigate_to,
        "open_menu": _handle_open_menu,
        "close_menu": _handle_close_menu,
        "advance_dialog": _handle_advance_dialog,
        "select_option": _handle_select_option,
        "click_button": _handle_advance_dialog,
        "use_skill": _handle_use_skill,
        "basic_attack": _handle_basic_attack,
        "observe": _handle_observe,
        "wait": _handle_observe,
        "look": _handle_observe,
        "go_back": _handle_go_back,
        "confirm": _handle_confirm,
        "interact": _handle_interact,
        "jump": _handle_jump,
        "dash": _handle_dash,
        "sprint": _handle_sprint,
        "swim": _handle_swim,
        "select_quest": _handle_advance_dialog,
        "claim_reward": _handle_confirm,
        "select_item": _handle_select_option,
        "buy_item": _handle_confirm,
        "use_item": _handle_confirm,
        "teleport": _handle_confirm,
        "track_quest": _handle_advance_dialog,
        "toggle_auto": _handle_unknown,
    }


def create_genshin_agent(
    goal: str,
    window_title: str,
    api_key: str | None = None,
    max_iterations: int = 100,
    action_interval_sec: float = 1.5,
    state_sample_interval_sec: float = 3.0,
    plan_interval_sec: float = 15.0,
) -> tuple[AutonomousTaskBrain, GenshinPerceptionProvider, SafeWindowInputBackend]:
    """Factory that creates all components for the Genshin game agent."""
    import os
    os.environ.setdefault("AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW", "1")

    key = api_key or get_secret("ZHIPU_API_KEY") or ""

    # Input backend
    backend = SafeWindowInputBackend(
        target_window_title=window_title,
        pixels_per_degree=8.0,
    )

    # Perception
    perception = GenshinPerceptionProvider(
        window_title=window_title,
        api_key=key,
    )

    # Action executor
    executor = GenshinActionExecutor(backend)

    # Brain config
    config = TaskBrainConfig(
        capsule_id="genshin_main",
        game_id="genshin",
        max_iterations=max_iterations,
        action_interval_sec=action_interval_sec,
        state_sample_interval_sec=state_sample_interval_sec,
        plan_interval_sec=plan_interval_sec,
        require_confirmation_risk="high",
        require_claim_verification=False,  # Disabled for faster iteration
    )

    # Task brain
    brain = AutonomousTaskBrain(
        perception=perception,
        executor=executor,
        config=config,
    )

    return brain, perception, backend

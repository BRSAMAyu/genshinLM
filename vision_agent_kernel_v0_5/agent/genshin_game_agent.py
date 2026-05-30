"""Genshin Impact autonomous game agent.

Connects the kernel pipeline to AutonomousTaskBrain for real Genshin gameplay.
Uses dxcam for capture, Zhipu GLM-4V for VLM, GenshinScreenClassifier for
screen state, and SafeWindowInputBackend for input.

Usage:
    python scripts/run_genshin_agent.py --goal "完成主线任务" --window-title "原神"
"""
from __future__ import annotations

import base64
import io
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Any

import numpy as np

from agent.autonomous_task_brain import AutonomousTaskBrain, ActionExecutor, PerceptionProvider, TaskBrainConfig
from core.local_secret_store import get_secret
from core.state_bus import StateBus
from core.timebase import Timebase
from execution.safe_window_backend import SafeWindowInputBackend, SafeWindowInputError
from planning.screen_state_claim_builder import ClassifierOutput, OcrOutput, VLMOutput

log = logging.getLogger(__name__)

_VLM_PROMPT = (
    'Analyze this Genshin Impact screenshot. Return strict JSON only:\n'
    '{\n'
    '  "screen_state": "overworld|combat|turn_based_combat|dialog|menu|'
    'map|loading|inventory|shop|quest_log|reward_screen|boss_fight|cutscene|unknown",\n'
    '  "player_status": {"hp":"high/medium/low","stamina":"high/medium/low","location":"description"},\n'
    '  "visible_objects": [{"type":"enemy|npc|item|chest|waypoint","description":"...","'
    'position":"center|left|right","screen_x":0.5,"screen_y":0.5}],\n'
    '  "ui_elements": {"element_id":"visible_text_or_label","click_x":0.5,"click_y":0.5},\n'
    '  "scene_description": "what is happening on screen",\n'
    '  "death_screen": false,\n'
    '  "suggested_action": "what the player should do next"\n'
    '}'
)

_PERMANENT_HTTP_CODES = {401, 403}


def _encode_frame_jpeg(frame: np.ndarray, max_long_side: int = 1280) -> bytes:
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
    rgb = frame[:, :, ::-1] if frame.shape[-1] == 3 else frame
    img = Image.fromarray(rgb)
    if max(h, w) > max_long_side:
        scale = max_long_side / max(h, w)
        img = img.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class GenshinPerceptionProvider:
    """PerceptionProvider with async VLM, optional external frame source."""

    def __init__(
        self,
        window_title: str,
        api_key: str | None = None,
        external_capturer: Any | None = None,
    ) -> None:
        self._api_key = api_key or get_secret("ZHIPU_API_KEY") or ""
        self._timebase = Timebase()
        self._frame_id = 0
        self._started = False

        # Screen capture — use external if provided (shares kernel pipeline)
        if external_capturer is not None:
            self._capturer = external_capturer
            self._owns_capturer = False
        else:
            from perception.dxcam_capture import DxcamCapturer, CaptureConfig
            self._capturer = DxcamCapturer(CaptureConfig(target_fps=15.0), timebase=self._timebase)
            self._owns_capturer = True

        from perception.genshin_screen_classifier import GenshinScreenClassifier
        self._classifier = GenshinScreenClassifier()

        # VLM async infrastructure
        self._vlm_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self._vlm_model = "glm-4v-flash"
        self._vlm_lock = threading.Lock()
        self._vlm_result: VLMOutput | None = None
        self._vlm_frame: np.ndarray | None = None
        self._vlm_thread: threading.Thread | None = None
        self._vlm_stop = threading.Event()
        self._vlm_consecutive_failures = 0
        self._vlm_circuit_open_until = 0.0
        self._vlm_interval = 3.0

    def start(self) -> None:
        if self._owns_capturer:
            self._capturer.start()
        self._vlm_stop.clear()
        self._vlm_thread = threading.Thread(target=self._vlm_loop, name="vlm-async", daemon=True)
        self._vlm_thread.start()
        self._started = True
        log.info("[GenshinPerception] Started capture + VLM thread")

    def stop(self) -> None:
        self._vlm_stop.set()
        if self._vlm_thread is not None:
            self._vlm_thread.join(timeout=5.0)
            self._vlm_thread = None
        if self._owns_capturer and self._started:
            self._capturer.stop()
        self._started = False

    def capture_frame(self) -> np.ndarray | None:
        try:
            packet = self._capturer.get_latest_frame()
        except Exception as exc:
            log.warning("[GenshinPerception] capture_frame error: %s", exc)
            return None
        if packet is None:
            return None
        self._frame_id = packet.frame_id
        return packet.image

    def analyze_vlm(self, frame: np.ndarray, game_id: str) -> VLMOutput | None:
        # Submit frame for async analysis
        with self._vlm_lock:
            self._vlm_frame = frame
        # Return cached result immediately (non-blocking)
        with self._vlm_lock:
            return self._vlm_result

    def classify_screen(self, frame: np.ndarray) -> ClassifierOutput | None:
        try:
            result = self._classifier.classify(frame)
            return ClassifierOutput(
                screen_state=result.state,
                confidence=result.confidence,
                source="genshin_classifier",
            )
        except Exception as exc:
            log.warning("[GenshinPerception] classify_screen error: %s", exc)
            return None

    def ocr_scan(self, frame: np.ndarray) -> list[OcrOutput]:
        return []

    # --- VLM background thread ---

    def _vlm_loop(self) -> None:
        while not self._vlm_stop.is_set():
            frame = self._get_pending_frame()
            if frame is not None:
                result = self._call_vlm(frame)
                if result is not None:
                    with self._vlm_lock:
                        self._vlm_result = result
            self._vlm_stop.wait(self._vlm_interval)

    def _get_pending_frame(self) -> np.ndarray | None:
        with self._vlm_lock:
            frame = self._vlm_frame
            self._vlm_frame = None
            return frame

    def _call_vlm(self, frame: np.ndarray) -> VLMOutput | None:
        if not self._api_key:
            return None
        now = time.perf_counter()
        if now < self._vlm_circuit_open_until:
            return None
        try:
            jpeg = _encode_frame_jpeg(frame, max_long_side=1280)
            img_b64 = base64.b64encode(jpeg).decode("ascii")
            payload = {
                "model": self._vlm_model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VLM_PROMPT},
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
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._extract_json(text)
            self._vlm_consecutive_failures = 0
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
        except urllib.error.HTTPError as exc:
            self._vlm_consecutive_failures += 1
            if exc.code in _PERMANENT_HTTP_CODES:
                self._vlm_circuit_open_until = now + 300.0
                log.error("[GenshinPerception] VLM permanent error %d — circuit open for 5min", exc.code)
            else:
                backoff = min(2 ** self._vlm_consecutive_failures, 60.0)
                self._vlm_circuit_open_until = now + backoff
                log.warning("[GenshinPerception] VLM HTTP %d — backoff %.0fs (failures=%d)",
                            exc.code, backoff, self._vlm_consecutive_failures)
            return None
        except Exception as exc:
            self._vlm_consecutive_failures += 1
            backoff = min(2 ** self._vlm_consecutive_failures, 60.0)
            self._vlm_circuit_open_until = now + backoff
            log.warning("[GenshinPerception] VLM failed: %s — backoff %.0fs", exc, backoff)
            return None

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass
        return None


class GenshinActionExecutor:
    """Translates semantic actions into Genshin key/mouse inputs."""

    def __init__(
        self,
        backend: SafeWindowInputBackend,
        shutdown_event: threading.Event | None = None,
        viewport: tuple[int, int] = (1920, 1080),
    ) -> None:
        self._backend = backend
        self._shutdown = shutdown_event or threading.Event()
        self._viewport = viewport
        self._timebase = Timebase()

    def execute_semantic(self, action: str, target: str, context: dict[str, Any]) -> bool:
        log.info("[GenshinExecutor] action=%s target=%s", action, target)
        handler = self._ACTION_MAP.get(action, self._handle_unknown)
        try:
            return handler(self, target, context)
        except SafeWindowInputError as exc:
            log.warning("[GenshinExecutor] Focus/input error on %s: %s — pausing", action, exc)
            self._interruptible_wait(0.5)
            return False
        except Exception as exc:
            log.warning("[GenshinExecutor] Action %s failed: %s", action, exc)
            return False

    def is_target_focused(self) -> bool:
        return self._backend.is_target_focused()

    def _interruptible_wait(self, seconds: float) -> bool:
        """Wait in 50ms chunks. Returns False if shutdown was requested."""
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            if self._shutdown.is_set():
                return False
            time.sleep(min(0.05, deadline - time.perf_counter()))
        return True

    def _hold_keys_for(self, keys: list[str], reason: str, seconds: float) -> bool:
        """Hold keys for duration, interruptible. Returns False if interrupted."""
        for key in keys:
            try:
                self._backend.key_down(key, reason=f"{reason}_{key}")
            except Exception:
                self._release_keys(keys, reason)
                return False
        ok = self._interruptible_wait(seconds)
        self._release_keys(keys, reason)
        return ok

    def _release_keys(self, keys: list[str], reason: str) -> None:
        for key in reversed(keys):
            try:
                self._backend.key_up(key, reason=f"{reason}_{key}_done")
            except Exception:
                pass

    def _press_key_safe(self, key: str, reason: str, hold_sec: float = 0.1) -> bool:
        """key_down → wait → key_up with safety. Returns False if interrupted."""
        try:
            self._backend.key_down(key, reason=reason)
        except Exception:
            return False
        ok = self._interruptible_wait(hold_sec)
        try:
            self._backend.key_up(key, reason=f"{reason}_done")
        except Exception:
            pass
        return ok

    def _click_at_normalized(self, nx: float, ny: float, reason: str) -> bool:
        """Click at normalized (0-1) coordinates, converting to absolute screen coords."""
        try:
            rect = self._backend.client_rect()
            sx = rect.left + int(nx * rect.width)
            sy = rect.top + int(ny * rect.height)
            self._backend.click_at(sx, sy, reason=reason)
            return True
        except Exception as exc:
            log.warning("[GenshinExecutor] click_at failed: %s", exc)
            return False

    # --- Action handlers ---

    def _handle_move(self, target: str, context: dict[str, Any]) -> bool:
        direction = target.lower() if target else "forward"
        keys = self._parse_direction_keys(direction)
        return self._hold_keys_for(keys, "move", 1.5)

    def _handle_navigate_to(self, target: str, context: dict[str, Any]) -> bool:
        self._press_key_safe("m", "open_map", 0.5)
        if not self._interruptible_wait(1.5):
            return False
        # If VLM provided coordinates in context, click there
        coords = context.get("target_coords")
        if coords and isinstance(coords, (list, tuple)) and len(coords) == 2:
            ok = self._click_at_normalized(coords[0], coords[1], "navigate_to_target")
            if ok:
                self._interruptible_wait(1.0)
                self._press_key_safe("enter", "confirm_teleport", 0.3)
                return True
        log.warning("[GenshinExecutor] navigate_to: no coordinates for target=%s", target)
        return False

    def _handle_open_menu(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("esc", "open_menu", 0.3)

    def _handle_close_menu(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("esc", "close_menu", 0.3)

    def _handle_advance_dialog(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("space", "advance_dialog", 0.3)

    def _handle_select_option(self, target: str, context: dict[str, Any]) -> bool:
        if target and target.isdigit():
            return self._press_key_safe(target, f"select_option_{target}", 0.3)
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "select_option")
        return self._press_key_safe("1", "select_first_option", 0.3)

    def _handle_use_skill(self, target: str, context: dict[str, Any]) -> bool:
        skill_map = {"e": "e", "q": "q", "1": "1", "2": "2", "3": "3", "4": "4"}
        key = skill_map.get(target, "e")
        return self._press_key_safe(key, f"use_skill_{key}", 0.3)

    def _handle_basic_attack(self, target: str, context: dict[str, Any]) -> bool:
        try:
            self._backend.left_click(reason="basic_attack")
            return True
        except Exception:
            return False

    def _handle_observe(self, target: str, context: dict[str, Any]) -> bool:
        return self._interruptible_wait(2.0)

    def _handle_look(self, target: str, context: dict[str, Any]) -> bool:
        target = target.lower() if target else "center"
        delta_map: dict[str, tuple[float, float]] = {
            "left": (-15.0, 0.0), "right": (15.0, 0.0),
            "up": (0.0, -10.0), "down": (0.0, 10.0),
            "center": (0.0, 0.0),
        }
        dx, dy = delta_map.get(target, (0.0, 0.0))
        if dx != 0.0 or dy != 0.0:
            try:
                self._backend.mouse_move(dx, dy, reason=f"look_{target}")
            except Exception:
                return False
        return True

    def _handle_click_button(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords and isinstance(coords, (list, tuple)) and len(coords) == 2:
            return self._click_at_normalized(coords[0], coords[1], f"click_button_{target}")
        return self._press_key_safe("enter", f"click_button_{target}", 0.3)

    def _handle_select_quest(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "select_quest")
        if target and target.isdigit():
            return self._press_key_safe(target, f"select_quest_{target}", 0.3)
        return self._press_key_safe("enter", "select_quest", 0.3)

    def _handle_track_quest(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "track_quest")
        return self._press_key_safe("enter", "track_quest", 0.3)

    def _handle_toggle_auto(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("z", "toggle_auto", 0.3)

    def _handle_go_back(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("esc", "go_back", 0.3)

    def _handle_confirm(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("enter", "confirm", 0.3)

    def _handle_interact(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("f", "interact", 0.3)

    def _handle_jump(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("space", "jump", 0.15)

    def _handle_dash(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("shift", "dash", 0.2)

    def _handle_sprint(self, target: str, context: dict[str, Any]) -> bool:
        return self._hold_keys_for(["w", "shift"], "sprint", 2.0)

    def _handle_swim(self, target: str, context: dict[str, Any]) -> bool:
        return self._hold_keys_for(["w", "shift"], "swim", 1.5)

    def _handle_climb(self, target: str, context: dict[str, Any]) -> bool:
        return self._hold_keys_for(["w", "space"], "climb", 2.0)

    def _handle_glide(self, target: str, context: dict[str, Any]) -> bool:
        # Deploy glider then glide forward
        try:
            self._backend.left_click(reason="glide_deploy")
        except Exception:
            pass
        self._interruptible_wait(0.3)
        try:
            self._backend.key_down("space", reason="glide_deploy")
            self._interruptible_wait(0.15)
            self._backend.key_up("space", reason="glide_deployed")
        except Exception:
            pass
        return self._hold_keys_for(["w"], "glide", 2.0)

    def _handle_unknown(self, target: str, context: dict[str, Any]) -> bool:
        log.warning("[GenshinExecutor] Unknown action: %s", target)
        self._interruptible_wait(1.0)
        return False

    def _handle_dodge(self, target: str, context: dict[str, Any]) -> bool:
        direction = target.lower() if target else "forward"
        key_map = {"forward": "w", "back": "s", "left": "a", "right": "d"}
        move_key = key_map.get(direction, "w")
        try:
            self._backend.key_down(move_key, reason=f"dodge_move_{move_key}")
        except Exception:
            return False
        ok = self._press_key_safe("shift", "dodge", 0.2)
        try:
            self._backend.key_up(move_key, reason=f"dodge_move_{move_key}_done")
        except Exception:
            pass
        return ok

    def _handle_heal(self, target: str, context: dict[str, Any]) -> bool:
        slot = context.get("healer_slot", "4")
        self._press_key_safe(slot, "switch_healer", 0.3)
        self._interruptible_wait(0.5)
        return self._press_key_safe("e", "heal_skill", 0.3)

    def _handle_switch_char(self, target: str, context: dict[str, Any]) -> bool:
        char_map = {"1": "1", "2": "2", "3": "3", "4": "4"}
        slot = char_map.get(target, "1")
        return self._press_key_safe(slot, f"switch_char_{slot}", 0.3)

    def _handle_use_burst(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("q", "elemental_burst", 0.3)

    def _handle_use_ultimate(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("q", "ultimate", 0.3)

    def _handle_select_dialog_option(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords and isinstance(coords, (list, tuple)) and len(coords) == 2:
            return self._click_at_normalized(coords[0], coords[1], f"select_dialog_{target}")
        if target and target.isdigit():
            return self._press_key_safe(target, f"select_dialog_{target}", 0.3)
        return self._press_key_safe("1", "select_first_dialog_option", 0.3)

    def _handle_move_forward(self, target: str, context: dict[str, Any]) -> bool:
        return self._hold_keys_for(["w"], "move_forward", 1.5)

    def _handle_open_map(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("m", "open_map", 0.3)

    def _handle_close_map(self, target: str, context: dict[str, Any]) -> bool:
        return self._press_key_safe("m", "close_map", 0.3)

    def _handle_select_waypoint(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords and isinstance(coords, (list, tuple)) and len(coords) == 2:
            ok = self._click_at_normalized(coords[0], coords[1], "select_waypoint")
        else:
            ok = self._click_at_normalized(0.5, 0.5, "select_waypoint_center")
        if ok:
            self._interruptible_wait(0.5)
            self._press_key_safe("enter", "confirm_waypoint", 0.3)
        return ok

    def _handle_skip(self, target: str, context: dict[str, Any]) -> bool:
        self._press_key_safe("esc", "skip_cutscene_dialog", 0.3)
        self._interruptible_wait(0.5)
        return self._press_key_safe("enter", "skip_cutscene_confirm", 0.3)

    def _handle_claim_all(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "claim_all")
        return self._press_key_safe("enter", "claim_all", 0.3)

    def _handle_sort(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "sort")
        return self._press_key_safe("enter", "sort", 0.3)

    def _handle_buy_item(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "buy_item")
        return self._press_key_safe("enter", "buy_item", 0.3)

    def _handle_teleport(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "teleport")
        return self._press_key_safe("enter", "teleport", 0.3)

    def _handle_use_item(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "use_item")
        return self._press_key_safe("enter", "use_item", 0.3)

    def _handle_claim_reward(self, target: str, context: dict[str, Any]) -> bool:
        coords = context.get("target_coords")
        if coords:
            return self._click_at_normalized(coords[0], coords[1], "claim_reward")
        return self._press_key_safe("enter", "claim_reward", 0.3)

    @staticmethod
    def _parse_direction_keys(direction: str) -> list[str]:
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
        if not keys:
            key_map = {"forward": "w", "back": "s", "left": "a", "right": "d"}
            keys = [key_map.get(direction, "w")]
        return keys

    _ACTION_MAP: dict[str, Any] = {
        "move": _handle_move,
        "move_forward": _handle_move_forward,
        "navigate_to": _handle_navigate_to,
        "open_menu": _handle_open_menu,
        "close_menu": _handle_close_menu,
        "advance_dialog": _handle_advance_dialog,
        "select_option": _handle_select_option,
        "select_dialog_option": _handle_select_dialog_option,
        "click_button": _handle_click_button,
        "use_skill": _handle_use_skill,
        "use_burst": _handle_use_burst,
        "use_ultimate": _handle_use_ultimate,
        "basic_attack": _handle_basic_attack,
        "attack": _handle_basic_attack,
        "observe": _handle_observe,
        "wait": _handle_observe,
        "look": _handle_look,
        "go_back": _handle_go_back,
        "confirm": _handle_confirm,
        "interact": _handle_interact,
        "jump": _handle_jump,
        "dash": _handle_dash,
        "dodge": _handle_dodge,
        "sprint": _handle_sprint,
        "swim": _handle_swim,
        "climb": _handle_climb,
        "glide": _handle_glide,
        "select_quest": _handle_select_quest,
        "claim_reward": _handle_claim_reward,
        "claim_all": _handle_claim_all,
        "select_item": _handle_select_option,
        "buy_item": _handle_buy_item,
        "use_item": _handle_use_item,
        "teleport": _handle_teleport,
        "track_quest": _handle_track_quest,
        "toggle_auto": _handle_toggle_auto,
        "open_map": _handle_open_map,
        "close_map": _handle_close_map,
        "select_waypoint": _handle_select_waypoint,
        "skip": _handle_skip,
        "switch_char": _handle_switch_char,
        "heal": _handle_heal,
        "sort": _handle_sort,
    }


def create_genshin_agent(
    goal: str,
    window_title: str,
    api_key: str | None = None,
    max_iterations: int = 100,
    action_interval_sec: float = 1.5,
    state_sample_interval_sec: float = 3.0,
    plan_interval_sec: float = 15.0,
    state_bus: StateBus | None = None,
    external_capturer: Any | None = None,
) -> tuple[AutonomousTaskBrain, GenshinPerceptionProvider, SafeWindowInputBackend]:
    import os
    os.environ.setdefault("AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW", "1")

    key = api_key or get_secret("ZHIPU_API_KEY") or ""

    backend = SafeWindowInputBackend(
        target_window_title=window_title,
        pixels_per_degree=8.0,
    )

    perception = GenshinPerceptionProvider(
        window_title=window_title,
        api_key=key,
        external_capturer=external_capturer,
    )

    executor = GenshinActionExecutor(backend)

    config = TaskBrainConfig(
        capsule_id="genshin_main",
        game_id="genshin",
        max_iterations=max_iterations,
        action_interval_sec=action_interval_sec,
        state_sample_interval_sec=state_sample_interval_sec,
        plan_interval_sec=plan_interval_sec,
        require_confirmation_risk="high",
        require_claim_verification=False,
    )

    brain = AutonomousTaskBrain(
        perception=perception,
        executor=executor,
        config=config,
        state_bus=state_bus,
    )

    # Wire shutdown event so executor can check it
    executor._shutdown = brain._shutdown

    return brain, perception, backend

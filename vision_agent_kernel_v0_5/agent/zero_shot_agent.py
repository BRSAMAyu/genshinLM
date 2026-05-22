from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from core.timebase import Timebase
from execution.safe_window_backend import SafeWindowInputBackend
from llm.vision_provider import ImageInput


# ---------------------------------------------------------------------------
# Game-specific keymaps
# ---------------------------------------------------------------------------

GAME_KEYMAPS: dict[str, dict[str, str]] = {
    "genshin": {
        "move_forward": "w", "move_backward": "s", "move_left": "a", "move_right": "d",
        "jump": "space", "sprint": "shift", "interact": "f",
        "elemental_skill": "e", "elemental_burst": "q",
        "char_1": "1", "char_2": "2", "char_3": "3", "char_4": "4",
        "menu": "esc", "map": "m", "tab": "tab",
    },
    "hsr": {
        "move_forward": "w", "move_backward": "s", "move_left": "a", "move_right": "d",
        "interact": "f", "skill": "e", "basic_attack": "q",
        "ultimate_1": "1", "ultimate_2": "2", "ultimate_3": "3", "ultimate_4": "4",
        "speed_toggle": "v", "menu": "esc", "map": "m",
    },
}

GAME_WINDOW_TITLES: dict[str, dict[str, str | list[str]]] = {
    "genshin": {"title": "Genshin Impact", "alts": ["原神", "Genshin Impact"]},
    "hsr": {"title": "崩坏：星穹铁道", "alts": ["Honkai: Star Rail"]},
}

# ---------------------------------------------------------------------------
# VLM / LLM prompt templates
# ---------------------------------------------------------------------------

_VLM_ANALYSIS_PROMPT = """\
Analyze this game screenshot in detail. Return strict JSON only:
{
  "screen_state": "overworld|combat|dialog|menu|map|loading|unknown",
  "player_status": {
    "health": "full|damaged|critical|unknown",
    "stamina": "full|depleting|empty|unknown",
    "position_in_frame": "center|left|right|top|bottom"
  },
  "visible_objects": [
    {"type": "npc|enemy|item|resource|marker|waypoint|chest|boss|collectible",
     "position": "left|center_left|center|center_right|right",
     "distance": "near|medium|far",
     "description": "short description"}
  ],
  "ui_elements": {
    "interaction_prompt": "interaction text or null",
    "quest_text": "quest tracker text or null",
    "notification": "any toast or notification text or null"
  },
  "scene_description": "1-2 sentence description of the current scene",
  "suggested_action": "move_forward|turn_left|turn_right|interact|attack|open_menu|wait|done"
}

Game: {game_name}
"""

_LLM_PLANNING_PROMPT = """\
You are a game AI control assistant. You decide what keys to press based on visual analysis.

Current goal: {goal}
Current iteration: {iteration}/{max_iterations}
Game: {game_name}

Current game state (from visual analysis):
{vlm_analysis}

Available keys: {keymap}

Previous actions and results:
{history}

Plan 1-5 key presses to progress toward the goal. Return strict JSON only:
{{
  "reasoning": "why these actions",
  "actions": [
    {{"key": "key_name", "duration_ms": 300, "reason": "why"}}
  ],
  "expected_result": "what should change after these actions",
  "confidence": 0.8,
  "goal_progress": "how close to the goal",
  "should_stop": false
}}

Rules:
- Only use keys from the available keymap
- Duration in milliseconds (100-2000)
- Be conservative: prefer short actions you can verify
- Set should_stop=true if the goal appears achieved
"""

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AgentAction:
    key: str
    duration_ms: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VLMAnalysis:
    screen_state: str
    player_status: dict[str, str]
    visible_objects: list[dict[str, str]]
    ui_elements: dict[str, str]
    scene_description: str
    suggested_action: str
    latency_ms: float
    raw_text: str


@dataclass(frozen=True, slots=True)
class LLMPlan:
    reasoning: str
    actions: list[AgentAction]
    expected_result: str
    confidence: float
    goal_progress: str
    should_stop: bool
    latency_ms: float
    raw_text: str


@dataclass(slots=True)
class ZeroShotResult:
    ok: bool
    goal: str
    iterations: int
    actions_taken: int
    history: list[dict[str, Any]]
    final_analysis: str
    error: str | None = None


# ---------------------------------------------------------------------------
# API clients (lightweight, no external deps)
# ---------------------------------------------------------------------------

class _ZhipuAPIClient:
    """Minimal Zhipu API client for VLM and LLM calls."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout

    def chat(self, model: str, messages: list[dict[str, Any]], max_tokens: int = 1024) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "stream": False,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            self._base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Zhipu API call failed: {exc}") from exc

    @staticmethod
    def extract_content(data: dict[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected API response: {data}") from exc


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------

def _encode_frame_png(frame: Any) -> bytes:
    """Encode a numpy frame to PNG bytes. Tries cv2 first, then Pillow."""
    try:
        import cv2
        success, encoded = cv2.imencode(".png", frame)
        if success:
            return encoded.tobytes()
    except ImportError:
        pass
    try:
        from PIL import Image
        import io
        if frame.shape[2] == 3:
            rgb = frame[:, :, ::-1] if frame.dtype.name != "uint8" else frame
            img = Image.fromarray(rgb)
        else:
            img = Image.fromarray(frame)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        pass
    raise RuntimeError("Neither cv2 nor Pillow available for frame encoding")


def _frame_to_image_input(frame: Any, frame_id: int = 0) -> ImageInput:
    png_bytes = _encode_frame_png(frame)
    return ImageInput(data=png_bytes, mime_type="image/png", frame_id=frame_id)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"no JSON object in text: {text[:200]}")
    return json.loads(cleaned[start : end + 1])


# ---------------------------------------------------------------------------
# Main Agent
# ---------------------------------------------------------------------------

class ZeroShotAgent:
    """Zero-shot game control agent: capture → VLM understand → LLM plan → execute."""

    def __init__(
        self,
        game: str,
        goal: str,
        api_key: str,
        *,
        vlm_model: str = "glm-4v-flash",
        llm_model: str = "glm-5.1",
        base_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        window_title: str | None = None,
        alt_window_titles: list[str] | None = None,
        max_iterations: int = 30,
        action_interval_sec: float = 1.0,
        vlm_interval_sec: float = 3.0,
    ) -> None:
        self.game = game
        self.goal = goal
        self.max_iterations = max_iterations
        self.action_interval = action_interval_sec
        self.vlm_interval = vlm_interval_sec
        self._timebase = Timebase()
        self._api = _ZhipuAPIClient(api_key, base_url)
        self._vlm_model = vlm_model
        self._llm_model = llm_model
        self._keymap = GAME_KEYMAPS.get(game, GAME_KEYMAPS["genshin"])

        wt = window_title
        alts = alt_window_titles or []
        if not wt and game in GAME_WINDOW_TITLES:
            wt = str(GAME_WINDOW_TITLES[game]["title"])
            alts = list(GAME_WINDOW_TITLES[game].get("alts", []))
        if not wt:
            raise ValueError(f"Cannot determine window title for game={game!r}")

        self._input = SafeWindowInputBackend(
            target_window_title=wt,
            alt_window_titles=alts,
            timebase=self._timebase,
        )
        self._history: list[dict[str, Any]] = []
        self._capturer: Any = None

    def run(self) -> ZeroShotResult:
        self._ensure_window()
        self._start_capture()
        total_actions = 0
        final_analysis = ""
        error = None

        try:
            for i in range(1, self.max_iterations + 1):
                print(f"\n{'='*60}", flush=True)
                print(f"[ZeroShot] Iteration {i}/{self.max_iterations}", flush=True)

                # 1. Capture frame
                frame = self._capture_frame()
                if frame is None:
                    print("[ZeroShot] No frame captured, waiting...", flush=True)
                    time.sleep(1.0)
                    continue

                # 2. VLM analysis
                analysis = self._vlm_analyze(frame, i)
                final_analysis = analysis.scene_description
                print(f"[ZeroShot] Screen: {analysis.screen_state} | "
                      f"Objects: {len(analysis.visible_objects)} | "
                      f"Action: {analysis.suggested_action}", flush=True)

                # 3. LLM planning
                plan = self._llm_plan(analysis, i)
                print(f"[ZeroShot] Plan: {plan.reasoning[:100]}...", flush=True)
                print(f"[ZeroShot] Actions: {len(plan.actions)} | "
                      f"Confidence: {plan.confidence:.1%}", flush=True)

                # 4. Execute actions
                for action in plan.actions:
                    if not self._input.is_target_focused():
                        print("[ZeroShot] Target window lost focus, re-focusing...", flush=True)
                        try:
                            self._input.focus_target_window()
                        except Exception:
                            print("[ZeroShot] Cannot regain focus, stopping.", flush=True)
                            return self._build_result(False, i, total_actions, "window_focus_lost", final_analysis)

                    self._execute_action(action)
                    total_actions += 1
                    self._history.append({
                        "iteration": i,
                        "action": action.as_dict(),
                        "screen_before": analysis.screen_state,
                        "scene": analysis.scene_description[:200],
                    })
                    time.sleep(max(action.duration_ms / 1000.0, self.action_interval))

                # 5. Check if goal achieved
                if plan.should_stop:
                    print(f"[ZeroShot] Goal achieved! {plan.goal_progress}", flush=True)
                    return self._build_result(True, i, total_actions, None, final_analysis)

                # 6. Wait before next cycle
                wait = max(0.5, self.vlm_interval - len(plan.actions) * self.action_interval)
                time.sleep(wait)

        except KeyboardInterrupt:
            error = "interrupted_by_user"
            print("\n[ZeroShot] Interrupted by user.", flush=True)
        except Exception as exc:
            error = str(exc)
            print(f"\n[ZeroShot] Error: {exc}", flush=True)
        finally:
            self._stop_capture()
            self._input.release_all(reason="zero_shot_agent_done")

        return self._build_result(False, self.max_iterations, total_actions, error, final_analysis)

    def _ensure_window(self) -> None:
        print(f"[ZeroShot] Looking for window: {self._input.target_window_title}", flush=True)
        try:
            self._input.focus_target_window()
            rect = self._input.client_rect()
            print(f"[ZeroShot] Window found: {rect.width}x{rect.height}", flush=True)
        except Exception as exc:
            print(f"[ZeroShot] Window not found: {exc}", flush=True)
            print(f"[ZeroShot] Please open the game and try again.", flush=True)
            raise

    def _start_capture(self) -> None:
        try:
            import dxcam
            self._capturer = dxcam.create(output_color="RGB")
            self._capturer.start(target_fps=10)
            print("[ZeroShot] DXcam capture started", flush=True)
        except ImportError:
            try:
                from mss import mss
                self._capturer = mss()
                print("[ZeroShot] MSS capture started", flush=True)
            except ImportError:
                raise RuntimeError("Neither dxcam nor mss is installed. Install one: pip install dxcam or pip install mss")

    def _stop_capture(self) -> None:
        try:
            if hasattr(self._capturer, "stop"):
                self._capturer.stop()
            elif hasattr(self._capturer, "__exit__"):
                self._capturer.__exit__(None, None, None)
        except Exception:
            pass

    def _capture_frame(self) -> Any:
        import numpy as np
        try:
            if hasattr(self._capturer, "get_latest_frame"):
                frame = self._capturer.get_latest_frame()
                return np.asarray(frame) if frame is not None else None
        except Exception:
            pass
        try:
            if hasattr(self._capturer, "shot"):
                import numpy as np
                monitor = self._capturer.monitors[1] if self._capturer.monitors else None
                if monitor:
                    frame = np.array(self._capturer.grab(monitor))
                    return frame[:, :, :3]
        except Exception:
            pass
        return None

    def _vlm_analyze(self, frame: Any, iteration: int) -> VLMAnalysis:
        image_input = _frame_to_image_input(frame, frame_id=iteration)
        data_url = f"data:{image_input.mime_type};base64,{base64.b64encode(image_input.data).decode('ascii')}"

        prompt = _VLM_ANALYSIS_PROMPT.format(game_name=self.game)
        started = self._timebase.now()
        try:
            resp = self._api.chat(self._vlm_model, [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ], max_tokens=800)
            text = _ZhipuAPIClient.extract_content(resp)
            latency = (self._timebase.now() - started) * 1000.0
            try:
                parsed = _extract_json(text)
            except ValueError:
                parsed = {
                    "screen_state": "unknown",
                    "player_status": {},
                    "visible_objects": [],
                    "ui_elements": {},
                    "scene_description": text[:300],
                    "suggested_action": "wait",
                }
        except Exception as exc:
            latency = (self._timebase.now() - started) * 1000.0
            parsed = {
                "screen_state": "unknown",
                "player_status": {},
                "visible_objects": [],
                "ui_elements": {},
                "scene_description": f"VLM error: {exc}",
                "suggested_action": "wait",
            }
            text = str(exc)

        return VLMAnalysis(
            screen_state=str(parsed.get("screen_state", "unknown")),
            player_status=parsed.get("player_status", {}),
            visible_objects=parsed.get("visible_objects", []),
            ui_elements=parsed.get("ui_elements", {}),
            scene_description=str(parsed.get("scene_description", "")),
            suggested_action=str(parsed.get("suggested_action", "wait")),
            latency_ms=latency,
            raw_text=text,
        )

    def _llm_plan(self, analysis: VLMAnalysis, iteration: int) -> LLMPlan:
        history_str = self._format_history()
        prompt = _LLM_PLANNING_PROMPT.format(
            goal=self.goal,
            iteration=iteration,
            max_iterations=self.max_iterations,
            game_name=self.game,
            vlm_analysis=json.dumps(asdict(analysis), ensure_ascii=False, indent=2),
            keymap=json.dumps(self._keymap, indent=2),
            history=history_str,
        )
        started = self._timebase.now()
        try:
            resp = self._api.chat(self._llm_model, [
                {"role": "system", "content": "You are a game control AI. Return strict JSON only."},
                {"role": "user", "content": prompt},
            ], max_tokens=800)
            text = _ZhipuAPIClient.extract_content(resp)
            latency = (self._timebase.now() - started) * 1000.0
            try:
                parsed = _extract_json(text)
            except ValueError:
                parsed = {
                    "reasoning": text[:200],
                    "actions": [],
                    "expected_result": "unknown",
                    "confidence": 0.0,
                    "goal_progress": "parse_error",
                    "should_stop": False,
                }
        except Exception as exc:
            latency = (self._timebase.now() - started) * 1000.0
            text = str(exc)
            parsed = {
                "reasoning": f"LLM error: {exc}",
                "actions": [],
                "expected_result": "error",
                "confidence": 0.0,
                "goal_progress": "error",
                "should_stop": False,
            }

        actions = []
        for a in parsed.get("actions", []):
            key_name = str(a.get("key", ""))
            resolved = self._keymap.get(key_name) or self._keymap.get(key_name.lower())
            if resolved is None and len(key_name) == 1:
                resolved = key_name
            if resolved:
                actions.append(AgentAction(
                    key=resolved,
                    duration_ms=min(max(int(a.get("duration_ms", 300)), 50), 3000),
                    reason=str(a.get("reason", "")),
                ))

        return LLMPlan(
            reasoning=str(parsed.get("reasoning", "")),
            actions=actions,
            expected_result=str(parsed.get("expected_result", "")),
            confidence=float(parsed.get("confidence", 0.0)),
            goal_progress=str(parsed.get("goal_progress", "")),
            should_stop=bool(parsed.get("should_stop", False)),
            latency_ms=latency,
            raw_text=text,
        )

    def _execute_action(self, action: AgentAction) -> None:
        print(f"  [Action] {action.key} for {action.duration_ms}ms — {action.reason}", flush=True)
        try:
            if action.key in ("mouse_move", "look"):
                return
            self._input.key_down(action.key, reason=action.reason)
            time.sleep(action.duration_ms / 1000.0)
            self._input.key_up(action.key, reason=action.reason)
        except Exception as exc:
            print(f"  [Action] Failed: {exc}", flush=True)

    def _format_history(self, max_entries: int = 5) -> str:
        recent = self._history[-max_entries:]
        if not recent:
            return "No previous actions."
        lines = []
        for h in recent:
            lines.append(
                f"- Iteration {h['iteration']}: pressed '{h['action']['key']}' "
                f"for {h['action']['duration_ms']}ms — {h['action']['reason']}"
            )
        return "\n".join(lines)

    def _build_result(
        self, ok: bool, iterations: int, actions: int,
        error: str | None, final_analysis: str,
    ) -> ZeroShotResult:
        return ZeroShotResult(
            ok=ok,
            goal=self.goal,
            iterations=iterations,
            actions_taken=actions,
            history=self._history,
            final_analysis=final_analysis,
            error=error,
        )

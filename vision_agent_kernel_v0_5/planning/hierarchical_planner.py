from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from planning.mission_graph_v3 import MissionGraph, MissionGraphBuilder
from planning.screen_state_claim import ScreenStateClaim

log = logging.getLogger(__name__)

_DECOMPOSITION_PROMPT = """\
You are a game AI task planner. You decompose a high-level goal into a hierarchical plan.

Game: {game_id}
Current goal: {goal}
Current screen state: {screen_state}
Available actions in current state: {available_actions}

Decompose the goal into steps. Return strict JSON only:
{{
  "reasoning": "why this decomposition",
  "steps": [
    {{
      "label": "human-readable step name",
      "node_type": "subtask|action|verify",
      "semantic_action": "navigate_to|click_button|select_quest|claim_reward|open_menu|...",
      "target": "what to target",
      "expected_state": "what the screen should look like after",
      "precondition": "what must be true before",
      "verifier": "how to verify success",
      "risk_level": "low|medium|high",
      "children": [nested substeps...]
    }}
  ],
  "estimated_duration_sec": 60,
  "complexity": "simple|moderate|complex",
  "confidence": 0.8
}}

Rules:
- Each step must have a clear expected_state so it can be verified
- Use "children" for sub-tasks that need further decomposition
- Prefer short, verifiable steps over long uncertain ones
- Every path must end with a verify node
- Risk level "high" requires human confirmation before execution
- semantic_action must be one of: navigate_to, click_button, select_quest,
  claim_reward, claim_all, open_menu, close_menu, advance_dialog, select_option,
  select_dialog_option, teleport, track_quest, toggle_auto, use_skill, use_burst,
  use_ultimate, basic_attack, attack, observe, go_back, select_item, buy_item,
  use_item, confirm, interact, move_forward, open_map, close_map, select_waypoint,
  dodge, switch_char, heal, skip, look, jump, dash, sprint, swim, interact_npc,
  open_chest, use_waypoint, use_statue, open_quest_log, open_inventory,
  open_character_screen, scroll_down, scroll_up, select_tab, use_food, revive_char,
  skip_cutscene, wait_for_loading, dismiss_notification
"""


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    api_key: str | None = None
    base_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    model: str = "glm-5.1"
    timeout_sec: float = 30.0
    max_retries: int = 2


@dataclass(frozen=True, slots=True)
class PlanResult:
    graph: MissionGraph
    reasoning: str
    confidence: float
    complexity: str
    estimated_duration_sec: float
    latency_ms: float
    raw_text: str


class HierarchicalPlanner:
    """Decomposes user goals into hierarchical MissionGraphs using LLM."""

    def __init__(self, config: PlannerConfig | None = None) -> None:
        cfg = config or PlannerConfig()
        self._api_key = cfg.api_key or os.getenv("ZHIPU_API_KEY", "")
        self._base_url = cfg.base_url
        self._model = cfg.model
        self._timeout = cfg.timeout_sec
        self._max_retries = cfg.max_retries

    def plan(
        self,
        goal: str,
        capsule_id: str,
        current_state: ScreenStateClaim,
        available_actions: list[str] | None = None,
    ) -> PlanResult:
        started = time.perf_counter()
        if not self._api_key:
            return self._fallback_plan(goal, capsule_id, current_state, started)
        actions_str = ", ".join(available_actions) if available_actions else "unknown"
        prompt = _DECOMPOSITION_PROMPT.format(
            game_id=current_state.game_id,
            goal=goal,
            screen_state=current_state.screen_state,
            available_actions=actions_str,
        )
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._call_llm(prompt)
                text = self._extract_content(resp)
                latency_ms = (time.perf_counter() - started) * 1000.0
                parsed = self._parse_json(text)
                graph = self._build_graph(goal, capsule_id, parsed)
                return PlanResult(
                    graph=graph,
                    reasoning=str(parsed.get("reasoning", "")),
                    confidence=float(parsed.get("confidence", 0.5)),
                    complexity=str(parsed.get("complexity", "moderate")),
                    estimated_duration_sec=float(parsed.get("estimated_duration_sec", 60)),
                    latency_ms=latency_ms,
                    raw_text=text,
                )
            except Exception as exc:
                if attempt == self._max_retries:
                    log.warning("Planner failed after %d attempts: %s", attempt + 1, exc)
                    return self._fallback_plan(goal, capsule_id, current_state, started)
                log.debug("Planner attempt %d failed: %s", attempt + 1, exc)

        return self._fallback_plan(goal, capsule_id, current_state, started)

    def _call_llm(self, prompt: str) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "You are a game AI task planner. Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "stream": False,
            "max_tokens": 2000,
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
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(response.read)
                try:
                    body = future.result(timeout=self._timeout)
                except concurrent.futures.TimeoutError:
                    raise TimeoutError("LLM response read timeout")
            return json.loads(body.decode("utf-8"))

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        return str(data["choices"][0]["message"]["content"])

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError(f"no JSON in planner response: {text[:200]}")
        return json.loads(cleaned[start:end + 1])

    @staticmethod
    def _build_graph(goal: str, capsule_id: str, parsed: dict[str, Any]) -> MissionGraph:
        steps = parsed.get("steps", [])
        if not steps:
            steps = [{"label": goal, "node_type": "action", "semantic_action": "observe"}]
        steps = [_sanitize_step(step) for step in steps if isinstance(step, dict)]
        return MissionGraphBuilder.from_decomposition(goal, capsule_id, steps)

    @staticmethod
    def _fallback_plan(
        goal: str,
        capsule_id: str,
        state: ScreenStateClaim,
        started: float,
    ) -> PlanResult:
        graph = MissionGraphBuilder.from_decomposition(goal, capsule_id, [
            {"label": f"Observe and assess: {goal}", "node_type": "action",
             "semantic_action": "observe", "expected_state": "screen analyzed"},
            {"label": f"Execute: {goal}", "node_type": "action",
             "semantic_action": "observe", "expected_state": "goal progress"},
        ])
        return PlanResult(
            graph=graph,
            reasoning="Fallback plan: LLM planner failed, using observe-and-act loop",
            confidence=0.3,
            complexity="unknown",
            estimated_duration_sec=120,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            raw_text="fallback",
        )


_ALLOWED_SEMANTIC_ACTIONS = {
    "navigate_to", "click_button", "select_quest", "claim_reward", "claim_all",
    "open_menu", "close_menu", "advance_dialog", "select_option",
    "select_dialog_option", "teleport", "track_quest", "toggle_auto",
    "use_skill", "use_burst", "use_ultimate", "basic_attack", "attack",
    "observe", "go_back", "select_item", "buy_item", "use_item", "confirm",
    "interact", "move_forward", "open_map", "close_map", "select_waypoint",
    "dodge", "switch_char", "heal", "skip", "look", "jump", "dash",
    "sprint", "swim", "climb", "glide",
    "interact_npc", "open_chest", "use_waypoint", "use_statue",
    "open_quest_log", "open_inventory", "open_character_screen",
    "scroll_down", "scroll_up", "select_tab", "use_food", "revive_char",
    "skip_cutscene", "wait_for_loading", "dismiss_notification",
}


def _sanitize_step(step: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(step)
    semantic_action = str(sanitized.get("semantic_action", "observe"))
    if semantic_action not in _ALLOWED_SEMANTIC_ACTIONS:
        sanitized["semantic_action"] = "observe"
        sanitized["target"] = "full_screen"
        sanitized["risk_level"] = "low"
        sanitized["metadata"] = {"sanitized_from": semantic_action}
    risk = str(sanitized.get("risk_level", "low")).lower()
    if risk not in {"low", "medium", "high", "critical"}:
        sanitized["risk_level"] = "medium"
    children = sanitized.get("children")
    if isinstance(children, list):
        sanitized["children"] = [_sanitize_step(child) for child in children if isinstance(child, dict)]
    return sanitized

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease
from core.types import SkillResult
from execution.input_worker import InputWorker
from app_service.recorder_backends import RecorderBackend, RecorderContext, backend_by_name


SkillType = Literal["ui", "navigation", "combat", "recovery", "verification"]


@dataclass(frozen=True, slots=True)
class SkillStep:
    step_id: str
    type: str
    label: str = ""
    delay_ms: int = 0
    timeout_ms: int = 1000
    interruptible: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    skill_id: str
    name: str
    type: SkillType
    version: int
    metadata: dict[str, Any]
    environment_profile: str
    preconditions: list[str]
    steps: list[SkillStep]
    visual_triggers: dict[str, dict[str, Any]]
    success_criteria: list[str]
    failure_policy: dict[str, Any]
    cleanup: list[dict[str, Any]]
    safety: dict[str, Any]
    capsule_id: str = "core"
    capabilities: list[str] = field(default_factory=list)
    parameters_schema: dict[str, Any] = field(default_factory=dict)
    resources: list[dict[str, Any]] = field(default_factory=list)
    verifier_contracts: list[dict[str, Any]] = field(default_factory=list)
    planner: dict[str, Any] = field(default_factory=dict)
    semantic_actions: list[dict[str, Any]] = field(default_factory=list)
    ui_anchors: list[str] = field(default_factory=list)
    capabilities_required: list[str] = field(default_factory=list)
    capabilities_provided: list[str] = field(default_factory=list)
    failure_modes: list[dict[str, Any]] = field(default_factory=list)
    fallbacks: list[dict[str, Any]] = field(default_factory=list)
    profile_compatibility: dict[str, Any] = field(default_factory=dict)
    benchmark_stats: dict[str, Any] = field(default_factory=dict)
    archived: bool = False
    updated_at: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    event_type: str
    timestamp: float
    active_window_title: str
    observation_summary: dict[str, Any]
    target_state: str
    payload: dict[str, Any] = field(default_factory=dict)
    user_marker: str | None = None
    visual_trigger_marker: str | None = None
    focus_state: str = "UNKNOWN"
    roi_profile: str | None = None
    observation_frame_id: int | None = None
    visual_triggers: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillSegment:
    segment_id: str
    start_ts: float
    end_ts: float
    event_count: int
    reason: str


@dataclass(frozen=True, slots=True)
class SkillDraft:
    draft_id: str
    raw_events: list[RecordedEvent]
    segments: list[SkillSegment]
    suggested_preconditions: list[str]
    suggested_visual_checkpoints: list[str]
    suggested_success_criteria: list[str]
    suggested_fallbacks: list[str]
    suggestions: list[str]


@dataclass(slots=True)
class RecordingSession:
    session_id: str
    started_at: float
    active_window_title: str
    backend_name: str = "mock"
    focus_state: str = "UNKNOWN"
    roi_profile: str = "default_1920x1080"
    events: list[RecordedEvent] = field(default_factory=list)


class SkillValidationError(ValueError):
    pass


class SkillRecorder:
    def __init__(self) -> None:
        self._session: RecordingSession | None = None
        self._backend: RecorderBackend = backend_by_name("mock")
        self._last_draft: SkillDraft | None = None

    @property
    def current(self) -> RecordingSession | None:
        return self._session

    @property
    def last_draft(self) -> SkillDraft | None:
        return self._last_draft

    def start(
        self,
        active_window_title: str = "dry-run",
        backend_name: str = "mock",
        focus_state: str = "UNKNOWN",
        roi_profile: str = "default_1920x1080",
        observation_frame_id: int | None = None,
        target_state: str = "UNKNOWN",
        visual_triggers: dict[str, bool] | None = None,
    ) -> RecordingSession:
        context = RecorderContext(
            active_window_title=active_window_title,
            focus_state=focus_state,
            roi_profile=roi_profile,
            observation_frame_id=observation_frame_id,
            target_state=target_state,
            visual_triggers=visual_triggers or {},
        )
        self._backend = backend_by_name(backend_name)
        self._backend.validate_context(context)
        self._session = RecordingSession(
            session_id=str(uuid.uuid4()),
            started_at=time.time(),
            active_window_title=active_window_title,
            backend_name=self._backend.name,
            focus_state=focus_state,
            roi_profile=roi_profile,
        )
        for event in self._backend.seed_events(context):
            self.add_event(**event)
        return self._session

    def add_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        marker: str | None = None,
        timestamp: float | None = None,
        target_state: str | None = None,
        focus_state: str | None = None,
        roi_profile: str | None = None,
        observation_frame_id: int | None = None,
        visual_triggers: dict[str, bool] | None = None,
        visual_trigger_marker: str | None = None,
    ) -> None:
        if self._session is None:
            return
        self._session.events.append(
            RecordedEvent(
                event_type=event_type,
                timestamp=timestamp or time.time(),
                active_window_title=self._session.active_window_title,
                observation_summary={
                    "frame_id": observation_frame_id,
                    "source": self._session.backend_name,
                    "roi_profile": roi_profile or self._session.roi_profile,
                    "visual_triggers": visual_triggers or {},
                },
                target_state=target_state or "UNKNOWN",
                payload=payload or {},
                user_marker=marker,
                visual_trigger_marker=visual_trigger_marker,
                focus_state=focus_state or self._session.focus_state,
                roi_profile=roi_profile or self._session.roi_profile,
                observation_frame_id=observation_frame_id,
                visual_triggers=visual_triggers or {},
            )
        )

    def stop(self) -> SkillDraft:
        if self._session is None:
            raise RuntimeError("no active recording session")
        session = self._session
        if not session.events:
            context = RecorderContext(session.active_window_title, session.focus_state, session.roi_profile)
            for event in backend_by_name("mock").seed_events(context):
                self.add_event(**event)
        draft = self._make_draft(session)
        self._last_draft = draft
        self._session = None
        return draft

    def _make_draft(self, session: RecordingSession) -> SkillDraft:
        segments: list[SkillSegment] = []
        if session.events:
            start = session.events[0].timestamp
            prev = session.events[0].timestamp
            count = 0
            last_target_state = session.events[0].target_state
            burst_count = 0
            for event in session.events:
                gap = event.timestamp - prev
                reason = ""
                if gap > 0.7:
                    reason = "pause_gap"
                elif event.user_marker:
                    reason = "user_marker"
                elif event.target_state != last_target_state and {event.target_state, last_target_state} & {"LOST", "TRACKED", "COASTING"}:
                    reason = "target_lost_or_reacquired"
                elif event.visual_trigger_marker or event.visual_triggers:
                    reason = "visual_state_change"
                elif event.event_type in {"key_down", "key_up", "mouse_click", "mouse_move"}:
                    burst_count += 1
                    if burst_count >= 6:
                        reason = "action_burst_grouping"
                        burst_count = 0
                else:
                    burst_count = 0
                if count and reason:
                    segments.append(
                        SkillSegment(str(uuid.uuid4()), start, prev, count, reason)
                    )
                    start = event.timestamp
                    count = 0
                count += 1
                prev = event.timestamp
                last_target_state = event.target_state
            segments.append(SkillSegment(str(uuid.uuid4()), start, prev, count, "recording_end"))
        return SkillDraft(
            draft_id=session.session_id,
            raw_events=session.events,
            segments=segments,
            suggested_preconditions=["require_focus", "target_visible"],
            suggested_visual_checkpoints=["wait_visual_trigger: action_completed"],
            suggested_success_criteria=["visual_action_completed"],
            suggested_fallbacks=["pause_and_reacquire", "fallback_basic_loop"],
            suggestions=[
                "这里建议加入 wait_visual_trigger: action_started",
                "这里如果目标丢失，建议 fallback: reacquire_target",
                "这里没有确认动作成功，建议加入 UI checkpoint",
            ],
        )

    def draft_to_skill_payload(
        self,
        draft: SkillDraft | None = None,
        skill_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        resolved = draft or self._last_draft
        if resolved is None:
            raise RuntimeError("no SkillDraft available to save")
        visual_triggers: dict[str, dict[str, Any]] = {
            trigger: {"type": "recorded_visual_trigger"}
            for event in resolved.raw_events
            for trigger, active in event.visual_triggers.items()
            if active
        }
        if not visual_triggers:
            visual_triggers = {"target_visible": {"type": "target_visible"}}
        steps: list[dict[str, Any]] = []
        down_keys: dict[str, RecordedEvent] = {}
        for event in resolved.raw_events:
            if event.event_type == "key_down" and "key" in event.payload:
                down_keys[str(event.payload["key"])] = event
            elif event.event_type == "key_up" and "key" in event.payload:
                key = str(event.payload["key"])
                down = down_keys.pop(key, None)
                lease_ms = 80 if down is None else max(20, min(1000, int((event.timestamp - down.timestamp) * 1000)))
                steps.append(
                    {
                        "step_id": f"key_tap_{len(steps) + 1}",
                        "type": "key_tap",
                        "label": f"Tap {key}",
                        "timeout_ms": max(lease_ms + 200, 300),
                        "interruptible": True,
                        "params": {"key": key, "lease_ms": lease_ms},
                    }
                )
            elif event.event_type == "mouse_move":
                steps.append(
                    {
                        "step_id": f"mouse_move_{len(steps) + 1}",
                        "type": "mouse_move",
                        "label": "Mouse move",
                        "timeout_ms": 300,
                        "interruptible": True,
                        "params": {"dx": event.payload.get("dx", 0), "dy": event.payload.get("dy", 0), "lease_ms": 50},
                    }
                )
            elif event.event_type == "mouse_click":
                steps.append(
                    {
                        "step_id": f"mouse_click_{len(steps) + 1}",
                        "type": "mouse_click",
                        "label": "Mouse click",
                        "timeout_ms": 300,
                        "interruptible": True,
                        "params": {"button": event.payload.get("button", "left"), "lease_ms": 80},
                    }
                )
            elif event.event_type == "wait":
                steps.append(
                    {
                        "step_id": f"wait_{len(steps) + 1}",
                        "type": "wait",
                        "label": "Wait",
                        "timeout_ms": int(event.payload.get("duration_ms", 100)),
                        "interruptible": True,
                        "params": {"duration_ms": int(event.payload.get("duration_ms", 100)), "chunk_ms": 100},
                    }
                )
        first_trigger = next(iter(visual_triggers))
        steps.append(
            {
                "step_id": f"checkpoint_{len(steps) + 1}",
                "type": "wait_visual_trigger",
                "label": f"Checkpoint {first_trigger}",
                "timeout_ms": 1200,
                "interruptible": True,
                "params": {"trigger": first_trigger, "chunk_ms": 100},
            }
        )
        profile = next((event.roi_profile for event in resolved.raw_events if event.roi_profile), "default_1920x1080")
        return {
            "skill_id": skill_id or f"recorded_{resolved.draft_id[:8]}",
            "name": name or "Recorded Test Window Skill",
            "type": "ui",
            "version": 1,
            "metadata": {"source": "recorder", "draft_id": resolved.draft_id},
            "capsule_id": "core",
            "capabilities": ["recorded_replay"],
            "parameters_schema": {"type": "object", "additionalProperties": True},
            "resources": [{"kind": "recording", "uri": f"recording:{resolved.draft_id}", "optional": False}],
            "verifier_contracts": [
                {
                    "verifier_id": "visual_checkpoint",
                    "requires": ["frame", "visual_trigger"],
                    "success_criteria": ["visual_action_completed"],
                }
            ],
            "planner": {
                "select_when": ["matching_preconditions", "requested_recorded_skill"],
                "cost": "low",
                "latency": "replay",
            },
            "environment_profile": profile,
            "preconditions": ["require_focus", "target_visible"],
            "steps": steps,
            "visual_triggers": visual_triggers,
            "success_criteria": ["visual_action_completed"],
            "failure_policy": {"max_retries": 1, "fallback": "pause_and_reacquire"},
            "cleanup": [{"type": "release_all"}],
            "safety": {"dry_run_default": True, "interruptible": True, "require_focus": True, "max_duration_ms": 8000},
        }


class SkillStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._skills_dir = root / "data" / "skills"
        self._versions_dir = self._skills_dir / "versions"
        self._index_path = self._skills_dir / "index.json"
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        self._versions_dir.mkdir(parents=True, exist_ok=True)
        if not self._index_path.exists():
            self._write_index({"skills": []})

    def list_skills(self) -> dict[str, Any]:
        index = self._read_index()
        return {"skills": [item for item in index.get("skills", []) if not item.get("archived", False)]}

    def get_skill(self, skill_id: str) -> SkillDefinition:
        path = self._skill_path(skill_id)
        if not path.exists():
            raise FileNotFoundError(f"skill not found: {skill_id}")
        return self._from_json(json.loads(path.read_text(encoding="utf-8")))

    def save_skill(self, payload: dict[str, Any]) -> SkillDefinition:
        incoming_version = int(payload.get("version", 1))
        skill_id = str(payload.get("skill_id") or self._slug(str(payload.get("name", "skill"))))
        if self._skill_path(skill_id).exists():
            current = self.get_skill(skill_id)
            incoming_version = current.version + 1
            version_path = self._versions_dir / f"{skill_id}.v{current.version}.json"
            version_path.write_text(json.dumps(self._to_json(current), indent=2), encoding="utf-8")
        skill = self._from_json({**payload, "skill_id": skill_id, "version": incoming_version})
        errors = SkillValidator(self._root).validate(skill)
        if errors:
            raise SkillValidationError("; ".join(errors))
        self._skill_path(skill.skill_id).write_text(json.dumps(self._to_json(skill), indent=2), encoding="utf-8")
        self._update_index(skill)
        return skill

    def archive_skill(self, skill_id: str) -> SkillDefinition:
        skill = self.get_skill(skill_id)
        archived = SkillDefinition(**{**asdict(skill), "archived": True, "updated_at": time.time()})
        self._skill_path(skill_id).write_text(json.dumps(self._to_json(archived), indent=2), encoding="utf-8")
        self._update_index(archived)
        return archived

    def versions(self, skill_id: str) -> dict[str, Any]:
        versions = sorted(self._versions_dir.glob(f"{skill_id}.v*.json"))
        return {"skill_id": skill_id, "versions": [path.name for path in versions]}

    def rollback(self, skill_id: str, version_file: str | None = None) -> SkillDefinition:
        versions = sorted(self._versions_dir.glob(f"{skill_id}.v*.json"))
        if not versions:
            raise FileNotFoundError(f"no versions found for skill: {skill_id}")
        selected = self._versions_dir / version_file if version_file else versions[-1]
        if not selected.exists():
            raise FileNotFoundError(f"version not found: {selected.name}")
        data = json.loads(selected.read_text(encoding="utf-8"))
        data["version"] = self.get_skill(skill_id).version + 1 if self._skill_path(skill_id).exists() else 1
        skill = self._from_json(data)
        self._skill_path(skill_id).write_text(json.dumps(self._to_json(skill), indent=2), encoding="utf-8")
        self._update_index(skill)
        return skill

    def _skill_path(self, skill_id: str) -> Path:
        return self._skills_dir / f"{self._slug(skill_id)}.json"

    def _slug(self, value: str) -> str:
        safe = "".join(char for char in value.lower().replace(" ", "_") if char.isalnum() or char in "-_")
        return safe or "skill"

    def _read_index(self) -> dict[str, Any]:
        try:
            text = self._index_path.read_text(encoding="utf-8")
            return json.loads(text) if text.strip() else {"skills": []}
        except (FileNotFoundError, json.JSONDecodeError):
            return {"skills": []}

    def _write_index(self, data: dict[str, Any]) -> None:
        tmp = self._index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._index_path)

    def _update_index(self, skill: SkillDefinition) -> None:
        index = self._read_index()
        items = [item for item in index.get("skills", []) if item.get("skill_id") != skill.skill_id]
        items.append(
            {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "type": skill.type,
                "version": skill.version,
                "archived": skill.archived,
                "updated_at": skill.updated_at,
            }
        )
        index["skills"] = items
        self._write_index(index)

    def _from_json(self, data: dict[str, Any]) -> SkillDefinition:
        steps = [
            SkillStep(
                step_id=str(step.get("step_id") or f"step_{index + 1}"),
                type=str(step["type"]),
                label=str(step.get("label", "")),
                delay_ms=int(step.get("delay_ms", 0)),
                timeout_ms=int(step.get("timeout_ms", 1000)),
                interruptible=bool(step.get("interruptible", True)),
                params=dict(step.get("params", {})),
            )
            for index, step in enumerate(data.get("steps", []))
        ]
        return SkillDefinition(
            skill_id=self._slug(str(data["skill_id"])),
            name=str(data["name"]),
            type=data.get("type", "ui"),
            version=int(data.get("version", 1)),
            metadata=dict(data.get("metadata", {})),
            environment_profile=str(data.get("environment_profile", "default_1920x1080")),
            preconditions=list(data.get("preconditions", [])),
            steps=steps,
            visual_triggers=dict(data.get("visual_triggers", {})),
            success_criteria=list(data.get("success_criteria", [])),
            failure_policy=dict(data.get("failure_policy", {"max_retries": 1})),
            cleanup=list(data.get("cleanup", [])),
            safety=dict(data.get("safety", {})),
            capsule_id=str(data.get("capsule_id", "core")),
            capabilities=list(data.get("capabilities", [])),
            parameters_schema=dict(data.get("parameters_schema", {})),
            resources=list(data.get("resources", [])),
            verifier_contracts=list(data.get("verifier_contracts", [])),
            planner=dict(data.get("planner", {})),
            semantic_actions=list(data.get("semantic_actions", [])),
            ui_anchors=list(data.get("ui_anchors", [])),
            capabilities_required=list(data.get("capabilities_required", [])),
            capabilities_provided=list(data.get("capabilities_provided", [])),
            failure_modes=list(data.get("failure_modes", [])),
            fallbacks=list(data.get("fallbacks", [])),
            profile_compatibility=dict(data.get("profile_compatibility", {})),
            benchmark_stats=dict(data.get("benchmark_stats", {})),
            archived=bool(data.get("archived", False)),
            updated_at=float(data.get("updated_at") or time.time()),
        )

    def _to_json(self, skill: SkillDefinition) -> dict[str, Any]:
        return asdict(skill)


class SkillValidator:
    def __init__(self, root: Path) -> None:
        self._root = root

    def validate(self, skill: SkillDefinition) -> list[str]:
        errors: list[str] = []
        safety = skill.safety
        if not safety.get("interruptible", False):
            errors.append("interruptible must be true")
        if not safety.get("require_focus", False):
            errors.append("require_focus must be true")
        if not safety.get("dry_run_default", True):
            errors.append("dry_run_default must remain true")
        max_duration = safety.get("max_duration_ms")
        if not isinstance(max_duration, int) or max_duration <= 0:
            errors.append("safety.max_duration_ms is required")
        if "max_retries" not in skill.failure_policy:
            errors.append("failure_policy.max_retries is required")
        if not skill.capsule_id:
            errors.append("capsule_id is required")
        for index, resource in enumerate(skill.resources):
            if not isinstance(resource, dict):
                errors.append(f"resources[{index}] must be an object")
                continue
            if not resource.get("kind"):
                errors.append(f"resources[{index}].kind is required")
            if not resource.get("uri"):
                errors.append(f"resources[{index}].uri is required")
        for index, contract in enumerate(skill.verifier_contracts):
            if not isinstance(contract, dict):
                errors.append(f"verifier_contracts[{index}] must be an object")
                continue
            if not contract.get("verifier_id"):
                errors.append(f"verifier_contracts[{index}].verifier_id is required")
            if not contract.get("success_criteria"):
                errors.append(f"verifier_contracts[{index}].success_criteria is required")
        for step in skill.steps:
            if not step.interruptible:
                errors.append(f"{step.step_id}: interruptible must be true")
            if step.type == "key_down":
                errors.append(f"{step.step_id}: permanent key_down is not allowed")
            if step.type.startswith("dangerous_") and not step.params.get("requires_confirmation", False):
                errors.append(f"{step.step_id}: dangerous action requires confirmation")
            if step.type == "wait_visual_trigger":
                trigger = str(step.params.get("trigger", ""))
                if trigger not in skill.visual_triggers:
                    errors.append(f"{step.step_id}: referenced visual trigger does not exist: {trigger}")
                chunk = int(step.params.get("chunk_ms", 100))
                if chunk <= 0 or chunk > 100:
                    errors.append(f"{step.step_id}: wait steps must be chunked at <=100ms")
        for index, action in enumerate(skill.semantic_actions):
            if not isinstance(action, dict):
                errors.append(f"semantic_actions[{index}] must be an object")
                continue
            if not action.get("intent"):
                errors.append(f"semantic_actions[{index}].intent is required")
            if action.get("kind") == "ui" and action.get("intent") in {"click_anchor", "click_text", "select_list_item"} and not action.get("target"):
                errors.append(f"semantic_actions[{index}].target is required for UI action")
            if {"x", "y"} <= set(action.get("parameters", {}).keys()) and not action.get("parameters", {}).get("anchor_id"):
                errors.append(f"semantic_actions[{index}] must not use raw x/y without anchor_id")
        if skill.safety.get("risk_level") in {"high", "human_confirm"} and not skill.verifier_contracts:
            errors.append("high risk skills require verifier_contracts")
        if skill.semantic_actions and not skill.verifier_contracts:
            errors.append("semantic skill requires verifier_contracts")
        profile = self._root / "configs" / "profiles" / f"{skill.environment_profile}.json"
        if not profile.exists():
            errors.append(f"referenced ROI/profile does not exist: {skill.environment_profile}")
        if not skill.steps:
            errors.append("skill must contain at least one step")
        return errors


class SkillDryRunRuntime:
    def run(self, skill: SkillDefinition) -> SkillResult:
        started = time.time()
        logs: list[str] = []
        status = "SUCCESS"
        failure_code = None
        for index, step in enumerate(skill.steps):
            logs.append(f"combo_step_start index={index} step={step.step_id} type={step.type}")
            if step.type == "branch_on_visual_state":
                logs.append("branch_on_visual_state resolved=dry_run_default")
            elif step.type in {"key_tap", "mouse_move", "mouse_click", "wait"}:
                logs.append(f"dry_run_event type={step.type} params={step.params}")
            elif step.type == "retry_until":
                logs.append("retry_until simulated once")
            elif step.type == "fallback_basic_loop":
                logs.append("fallback_basic_loop available")
            elif step.type == "pause_and_reacquire":
                logs.append("pause_and_reacquire checkpoint")
            elif step.type == "wait_visual_trigger":
                logs.append(f"wait_visual_trigger trigger={step.params.get('trigger')} chunk_ms={step.params.get('chunk_ms', 100)}")
            logs.append(f"combo_step_success index={index} step={step.step_id}")
        return SkillResult(
            skill_name=skill.name,
            status=status,
            failure_code=failure_code,
            started_at=started,
            finished_at=time.time(),
            payload={"dry_run": True, "logs": logs, "version": skill.version},
        )


class SkillReplayRuntime:
    def __init__(
        self,
        input_worker: InputWorker,
        state_bus: StateBus | None = None,
        timebase: Timebase | None = None,
        wait_chunk_ms: int = 100,
    ) -> None:
        self._input_worker = input_worker
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()
        self._wait_chunk_sec = max(0.001, min(wait_chunk_ms, 100) / 1000.0)

    def replay(
        self,
        skill: SkillDefinition,
        mode: Literal["dry-run", "safe-window"] = "dry-run",
        confirm: bool = False,
        focus_ok: bool = True,
    ) -> SkillResult:
        started = self._timebase.now()
        logs: list[str] = []
        leases_submitted = 0
        try:
            if mode == "safe-window":
                if not confirm:
                    raise RuntimeError("confirm_required: safe-window replay requires explicit user confirmation")
                if not focus_ok:
                    raise RuntimeError("safe replay requires target window focus")
            for step in skill.steps:
                self._check_interrupt()
                logs.append(f"replay_step_start step={step.step_id} type={step.type} mode={mode}")
                if mode == "dry-run":
                    logs.append(f"dry_run_replay type={step.type} params={step.params}")
                else:
                    leases_submitted += self._submit_step_lease(skill, step)
                if step.type == "wait":
                    self._chunked_wait(int(step.params.get("duration_ms", step.timeout_ms)))
                logs.append(f"replay_step_success step={step.step_id}")
            status = "SUCCESS"
            failure_code = None
        except Exception as exc:
            status = "FAILED"
            failure_code = str(exc)
            logs.append(f"replay_failed reason={failure_code}")
        return SkillResult(
            skill_name=skill.name,
            status=status,
            failure_code=failure_code,
            started_at=started,
            finished_at=self._timebase.now(),
            payload={"mode": mode, "logs": logs, "leases_submitted": leases_submitted},
        )

    def _submit_step_lease(self, skill: SkillDefinition, step: SkillStep) -> int:
        now = self._timebase.now()
        lease_ms = int(step.params.get("lease_ms", 80))
        if step.type == "key_tap":
            key_states = {str(step.params["key"]): "DOWN"}
            mouse_delta = None
        elif step.type == "mouse_move":
            key_states = {}
            mouse_delta = (float(step.params.get("dx", 0.0)), float(step.params.get("dy", 0.0)))
        elif step.type == "mouse_click":
            key_states = {f"mouse_{step.params.get('button', 'left')}": "DOWN"}
            mouse_delta = None
        else:
            return 0
        lease = InputLease(
            lease_id=str(uuid.uuid4()),
            owner=f"skill_replay:{skill.skill_id}",
            priority=35,
            key_states=key_states,
            mouse_delta=mouse_delta,
            created_at=now,
            expires_at=now + lease_ms / 1000.0,
            reason=f"skill_replay:{skill.skill_id}:{step.step_id}",
        )
        if not self._input_worker.submit_lease(lease):
            raise RuntimeError("input worker rejected replay lease")
        return 1

    def _chunked_wait(self, duration_ms: int) -> None:
        deadline = self._timebase.now() + max(0, duration_ms) / 1000.0
        while self._timebase.now() < deadline:
            self._check_interrupt()
            time.sleep(min(self._wait_chunk_sec, max(0.0, deadline - self._timebase.now())))

    def _check_interrupt(self) -> None:
        if self._state_bus is None:
            return
        interrupt = self._state_bus.next_interrupt(timeout=0.0)
        if interrupt is None:
            return
        if interrupt.priority <= 1:
            self._input_worker.submit_interrupt(interrupt)
            raise RuntimeError(f"replay interrupted: {interrupt.code}")
        self._state_bus.publish_interrupt(interrupt)

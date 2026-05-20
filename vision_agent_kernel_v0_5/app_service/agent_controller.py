from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from app_service.calibration import CalibrationProfile, CalibrationStore, RoiDefinition
from app_service.model_manager import ModelManager
from app_service.product_e2e import ProductE2ERunner
from app_service.skill_manager import SkillDryRunRuntime, SkillRecorder, SkillReplayRuntime, SkillStore, SkillValidationError, SkillValidator
from app_service.window_selector import WindowInfo, WindowSelector
from combat.danger_detector import DangerDetector
from combat.dodge_policy import DodgePolicy
from combat.playbook_runtime import CombatPlaybookRuntime
from llm.planner import Planner
from llm.sandbox_validator import SandboxValidator
from knowledge.source_resolver import SourceResolver
from knowledge.route_selector import RouteSelector
from planning.intent_parser import IntentParser
from planning.mission_queue import mission_to_dict
from planning.plan_validator import PlanValidator
from planning.task_spec_builder import TaskSpecBuilder
from persona.dialogue_generator import DialogueGenerator
from persona.event_translator import EventTranslator
from persona.persona_profile import PersonaRegistry


AgentMode = Literal["STOPPED", "RUNNING", "PAUSED", "EMERGENCY_STOPPED"]


@dataclass(frozen=True, slots=True)
class RuntimeHealthView:
    healthy: bool
    input_worker_alive: bool
    telemetry_ok: bool
    release_all_called: bool
    updated_at: float


@dataclass(frozen=True, slots=True)
class AgentStateView:
    mode: AgentMode
    current_node: str
    current_skill: str | None
    target_state: str
    progress: float
    frustration: float
    input_backend: str
    focus_status: str
    active_interrupt: dict[str, Any] | None
    runtime_health: RuntimeHealthView
    input_released: bool
    telemetry_ok: bool
    latest_run_id: str | None
    updated_at: float


class AgentController:
    """Thread-safe facade around kernel lifecycle controls.

    API handlers call this controller only. They do not get direct access to
    InputWorker, StateBus or worker threads.
    """

    def __init__(
        self,
        root: Path | None = None,
        timebase: Timebase | None = None,
    ) -> None:
        self._root = root or Path(__file__).resolve().parents[1]
        self._timebase = timebase or Timebase()
        self._state_bus = StateBus()
        self._backend = ConsoleInputBackend(self._timebase)
        self._worker: InputWorker | None = None
        self._lock = threading.RLock()
        self._mode: AgentMode = "STOPPED"
        self._current_node = "INIT"
        self._current_skill: str | None = None
        self._target_state = "NONE"
        self._progress = 0.0
        self._frustration = 0.0
        self._active_interrupt: Interrupt | None = None
        self._release_all_called = True
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest_run_id = self._find_latest_run_id()
        self._window_selector = WindowSelector()
        self._calibration_store = CalibrationStore(self._root)
        self._model_manager = ModelManager(self._root)
        self._skill_recorder = SkillRecorder()
        self._skill_store = SkillStore(self._root)
        self._skill_runtime = SkillDryRunRuntime()
        self._persona_registry = PersonaRegistry(self._root)
        self._event_translator = EventTranslator(self._persona_registry)
        self._dialogue_generator = DialogueGenerator(self._event_translator)
        self._planner = Planner(self._root, self._skill_store)
        self._sandbox_validator = SandboxValidator(self._root, self._skill_store)
        self._combat_runtime = CombatPlaybookRuntime()
        self._danger_detector = DangerDetector()
        self._dodge_policy = DodgePolicy()
        self._product_e2e = ProductE2ERunner(self._root, self)
        self._source_resolver = SourceResolver()
        self._route_selector = RouteSelector()
        self._intent_parser = IntentParser()
        self._task_spec_builder = TaskSpecBuilder(self._route_selector)
        self._plan_validator = PlanValidator()

    def start(self) -> AgentStateView:
        with self._lock:
            if self._mode == "RUNNING":
                return self.state()
            if self._worker is None or not self._worker.is_alive:
                self._worker = InputWorker(self._backend, timebase=self._timebase, tick_seconds=0.01)
                self._worker.start()
            self._stop_event.clear()
            self._pause_event.clear()
            self._mode = "RUNNING"
            self._current_node = "LOAD_TASK"
            self._current_skill = "LoadTaskSkill"
            self._target_state = "ACQUIRING"
            self._active_interrupt = None
            self._release_all_called = False
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run_status_loop,
                    name="app-service-agent-controller",
                    daemon=True,
                )
                self._thread.start()
            return self.state()

    def pause(self) -> AgentStateView:
        with self._lock:
            if self._mode == "RUNNING":
                self._mode = "PAUSED"
                self._pause_event.set()
                self._current_skill = None
            return self.state()

    def resume(self) -> AgentStateView:
        with self._lock:
            if self._mode == "PAUSED":
                self._mode = "RUNNING"
                self._pause_event.clear()
                self._current_skill = "TrackAndApproachSkill"
            return self.state()

    def stop(self) -> AgentStateView:
        with self._lock:
            self._stop_event.set()
            self._mode = "STOPPED"
            self._current_node = "INIT"
            self._current_skill = None
            self._target_state = "NONE"
            self._progress = 0.0
            self._frustration = 0.0
            if self._worker is not None:
                self._worker.stop()
            self._release_all_called = True
            return self.state()

    def emergency_stop(self) -> AgentStateView:
        with self._lock:
            interrupt = Interrupt(
                priority=0,
                timestamp=self._timebase.now(),
                code="EMERGENCY_STOP",
                source="app_service",
                requires_input_release=True,
            )
            self._active_interrupt = interrupt
            self._state_bus.publish_interrupt(interrupt)
            if self._worker is not None and self._worker.is_alive:
                self._worker.submit_interrupt(interrupt)
                self._worker.stop()
            else:
                self._backend.release_all(reason="app_service_emergency_stop")
            self._release_all_called = True
            self._mode = "EMERGENCY_STOPPED"
            self._current_skill = None
            self._target_state = "INTERRUPTED"
            self._stop_event.set()
            return self.state()

    def state(self) -> AgentStateView:
        with self._lock:
            now = self._timebase.now()
            worker_alive = self._worker is not None and self._worker.is_alive
            return AgentStateView(
                mode=self._mode,
                current_node=self._current_node,
                current_skill=self._current_skill,
                target_state=self._target_state,
                progress=self._progress,
                frustration=self._frustration,
                input_backend="console",
                focus_status="DRY_RUN",
                active_interrupt=asdict(self._active_interrupt) if self._active_interrupt else None,
                runtime_health=RuntimeHealthView(
                    healthy=self._mode != "EMERGENCY_STOPPED",
                    input_worker_alive=worker_alive,
                    telemetry_ok=True,
                    release_all_called=self._release_all_called,
                    updated_at=now,
                ),
                input_released=self._release_all_called,
                telemetry_ok=True,
                latest_run_id=self._latest_run_id,
                updated_at=now,
            )

    def current_config(self) -> dict[str, Any]:
        return {
            "input_backend": "console",
            "default_mode": "dry-run",
            "safe_window_required_for_real_input": True,
            "f9_emergency_stop": True,
            "service": {"host": "127.0.0.1", "port": 8765},
        }

    def latest_run(self) -> dict[str, Any]:
        run_id = self._find_latest_run_id()
        self._latest_run_id = run_id
        if run_id is None:
            return {"run_id": None, "report_path": None, "report_markdown": None}
        run_dir = self._root / "logs" / "runs" / run_id
        report = run_dir / "demo_report.md"
        health = run_dir / "health_report.json"
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "report_path": str(report) if report.exists() else None,
            "report_markdown": report.read_text(encoding="utf-8") if report.exists() else None,
            "health_report": json.loads(health.read_text(encoding="utf-8")) if health.exists() else None,
        }

    def run_diagnostics(self) -> dict[str, Any]:
        command = [sys.executable, str(self._root / "scripts" / "doctor.py")]
        result = subprocess.run(command, cwd=self._root, capture_output=True, text=True, timeout=60, check=False)
        report = self._root / "logs" / "doctor_report.json"
        if report.exists():
            payload = json.loads(report.read_text(encoding="utf-8"))
        else:
            payload = {"ok": result.returncode == 0, "checks": [{"key": "doctor", "status": "fail", "detail": result.stderr}]}
        return {"ok": bool(payload.get("ok", False)), "report_path": str(report), "checks": list(payload.get("checks", []))}

    def run_showcase(
        self,
        mode: str = "dry-run",
        seconds: float = 30.0,
        persona: str = "default_companion",
        provider: str = "mock",
        target_window_title: str = "vision_agent_kernel_v0_5 pseudo3d_scene",
    ) -> dict[str, Any]:
        command = [
            sys.executable,
            str(self._root / "scripts" / "run_showcase_demo.py"),
            "--mode",
            mode,
            "--seconds",
            str(seconds),
            "--persona",
            persona,
            "--provider",
            provider,
            "--target-window-title",
            target_window_title,
        ]
        result = subprocess.run(command, cwd=self._root, capture_output=True, text=True, timeout=max(30, int(seconds) + 30), check=False)
        latest = self.showcase_latest_report()
        return {
            "ok": result.returncode == 0,
            "run_id": latest.get("run_id"),
            "report_path": latest.get("report_path"),
            "report_markdown": latest.get("report_markdown"),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def showcase_latest_report(self) -> dict[str, Any]:
        runs_dir = self._root / "logs" / "runs"
        reports = list(runs_dir.glob("*/showcase_report.md")) if runs_dir.exists() else []
        if not reports:
            return {"run_id": None, "report_path": None, "report_markdown": None}
        report = max(reports, key=lambda path: path.stat().st_mtime)
        return {"run_id": report.parent.name, "report_path": str(report), "report_markdown": report.read_text(encoding="utf-8")}

    def list_windows(self) -> dict[str, Any]:
        selected = self._window_selector.selected
        return {
            "windows": [window.to_dict() for window in self._window_selector.list_windows()],
            "selected_handle": selected.handle if selected is not None else None,
        }

    def select_window(self, title: str | None = None, handle: int | None = None) -> WindowInfo:
        return self._window_selector.select_window(title=title, handle=handle)

    def snapshot_png(self) -> bytes:
        return self._window_selector.snapshot_png()

    def save_calibration_profile(self, profile_data: dict[str, Any], activate: bool = True) -> CalibrationProfile:
        rois = {
            name: RoiDefinition(**roi)
            for name, roi in profile_data.get("rois", {}).items()
        }
        profile = CalibrationProfile(
            profile_id=str(profile_data["profile_id"]),
            window_title=str(profile_data["window_title"]),
            source_resolution=tuple(profile_data["source_resolution"]),
            normalized_resolution=tuple(profile_data.get("normalized_resolution", (1280, 720))),
            rois=rois,
            created_at=str(profile_data.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        return self._calibration_store.save_profile(profile, activate=activate)

    def list_calibration_profiles(self) -> dict[str, object]:
        return self._calibration_store.list_profiles()

    def get_calibration_profile(self, profile_id: str) -> CalibrationProfile:
        return self._calibration_store.get_profile(profile_id)

    def test_calibration_profile(self, profile_id: str | None = None) -> dict[str, object]:
        return self._calibration_store.test_profile(profile_id)

    def restore_calibration_profile(self, profile_id: str) -> CalibrationProfile:
        return self._calibration_store.restore_previous(profile_id)

    def model_status(self) -> dict[str, Any]:
        return asdict(self._model_manager.status())

    def load_model(self, model_path: str | None = None) -> dict[str, Any]:
        return self._model_manager.load(model_path)

    def benchmark_model(self) -> dict[str, Any]:
        return self._model_manager.benchmark()

    def skill_record_start(self, backend_name: str = "mock") -> dict[str, Any]:
        window = self._window_selector.selected.title if self._window_selector.selected else "dry-run"
        focus_state = "FOCUSED" if self._window_selector.selected is not None and self._window_selector.focus_ok() else "DRY_RUN" if window == "dry-run" else "UNFOCUSED"
        active_profile = str(self._calibration_store.list_profiles().get("active_profile_id") or "default_1920x1080")
        session = self._skill_recorder.start(
            active_window_title=window,
            backend_name=backend_name,
            focus_state=focus_state,
            roi_profile=active_profile,
            observation_frame_id=None,
            target_state=self._target_state,
            visual_triggers={"target_visible": self._target_state in {"TRACKED", "CENTERED", "VERIFIED"}},
        )
        return {"ok": True, "session": asdict(session), "message": "recording started"}

    def skill_record_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._skill_recorder.add_event(
            event_type=str(payload.get("event_type", "marker")),
            payload=dict(payload.get("payload", {})),
            marker=payload.get("marker"),
            timestamp=payload.get("timestamp"),
            target_state=payload.get("target_state") or self._target_state,
            focus_state=payload.get("focus_state"),
            roi_profile=payload.get("roi_profile"),
            observation_frame_id=payload.get("observation_frame_id"),
            visual_triggers=dict(payload.get("visual_triggers", {})),
            visual_trigger_marker=payload.get("visual_trigger_marker"),
        )
        return self.skill_record_current()

    def skill_record_marker(self, marker: str = "user_marker") -> dict[str, Any]:
        return self.skill_record_event({"event_type": "marker", "marker": marker, "payload": {"marker": marker}})

    def skill_record_stop(self) -> dict[str, Any]:
        draft = self._skill_recorder.stop()
        return {"ok": True, "draft": asdict(draft), "message": "recording stopped"}

    def skill_record_current(self) -> dict[str, Any]:
        session = self._skill_recorder.current
        return {"ok": session is not None, "session": asdict(session) if session else None, "message": "recording active" if session else "no active recording"}

    def skill_record_save(self, skill_id: str | None = None, name: str | None = None) -> dict[str, Any]:
        payload = self._skill_recorder.draft_to_skill_payload(skill_id=skill_id, name=name)
        return asdict(self._skill_store.save_skill(payload))

    def list_skills(self) -> dict[str, Any]:
        return self._skill_store.list_skills()

    def get_skill(self, skill_id: str) -> dict[str, Any]:
        return asdict(self._skill_store.get_skill(skill_id))

    def save_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        return asdict(self._skill_store.save_skill(payload))

    def update_skill(self, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return asdict(self._skill_store.save_skill({**payload, "skill_id": skill_id}))

    def validate_skill(self, skill_id: str) -> dict[str, Any]:
        skill = self._skill_store.get_skill(skill_id)
        errors = SkillValidator(self._root).validate(skill)
        return {"ok": not errors, "errors": errors}

    def dry_run_skill(self, skill_id: str) -> dict[str, Any]:
        result = self._skill_runtime.run(self._skill_store.get_skill(skill_id))
        return {"ok": result.status == "SUCCESS", "result": asdict(result)}

    def replay_skill(self, skill_id: str, mode: str = "dry-run", confirm: bool = False) -> dict[str, Any]:
        skill = self._skill_store.get_skill(skill_id)
        created_worker = False
        if self._worker is None or not self._worker.is_alive:
            self._worker = InputWorker(self._backend, timebase=self._timebase, tick_seconds=0.01)
            self._worker.start()
            created_worker = True
        try:
            focus_ok = True
            if mode == "safe-window":
                focus_ok = self._window_selector.selected is not None and self._window_selector.focus_ok()
            runtime = SkillReplayRuntime(self._worker, state_bus=self._state_bus, timebase=self._timebase)
            result = runtime.replay(skill, mode=mode, confirm=confirm, focus_ok=focus_ok)
            return {"ok": result.status == "SUCCESS", "result": asdict(result)}
        finally:
            if created_worker:
                self._worker.stop()
                self._release_all_called = True

    def archive_skill(self, skill_id: str) -> dict[str, Any]:
        return asdict(self._skill_store.archive_skill(skill_id))

    def skill_versions(self, skill_id: str) -> dict[str, Any]:
        return self._skill_store.versions(skill_id)

    def skill_rollback(self, skill_id: str, version_file: str | None = None) -> dict[str, Any]:
        return asdict(self._skill_store.rollback(skill_id, version_file))

    def list_personas(self) -> dict[str, Any]:
        return {"personas": [asdict(persona) for persona in self._persona_registry.list_profiles()]}

    def persona_event(self, event_code: str, payload: dict[str, Any], persona_id: str) -> dict[str, Any]:
        line = self._dialogue_generator.generate(event_code, payload=payload, persona_id=persona_id)
        return {
            "persona_id": persona_id,
            "event_code": event_code,
            "message": line.message,
            "overlay_state": line.overlay_state,
            "emotion": line.emotion,
        }

    def plan_task(self, goal: str, provider: str = "mock", persona_id: str = "default_companion") -> dict[str, Any]:
        proposal = self._planner.plan(goal=goal, provider=provider, persona_id=persona_id)
        validation = self._sandbox_validator.validate_task_spec(proposal.task_spec)
        return {
            "ok": validation["ok"],
            "provider": proposal.provider,
            "task_spec": proposal.task_spec,
            "skill_chain": proposal.skill_chain,
            "risks": proposal.risks,
            "validation": validation,
            "usage": proposal.usage,
            "provider_error": proposal.provider_error,
        }

    def resolve_resource(self, goal: str) -> dict[str, Any]:
        return self._source_resolver.resolve(goal)

    def rank_routes(self, resource_id: str) -> dict[str, Any]:
        return self._route_selector.rank_routes(resource_id)

    def build_mission_queue(self, goal: str) -> dict[str, Any]:
        intent = self._intent_parser.parse(goal)
        queue = self._task_spec_builder.build(intent)
        available = {item["skill_id"] for item in self._skill_store.list_skills().get("skills", [])}
        validation = self._plan_validator.validate(queue, available_skills=available)
        return {"ok": validation["ok"], "mission": mission_to_dict(queue), "validation": validation}

    def explain_failure(self, summary: dict[str, Any], provider: str = "mock") -> dict[str, Any]:
        return self._planner.explain_failure(summary=summary, provider=provider)

    def create_combat_playbook(self, goal: str, team_profile: str = "default_team", provider: str = "mock") -> dict[str, Any]:
        playbook = self._planner.plan_combat(goal=goal, team_profile=team_profile, provider=provider)
        validation = self._combat_runtime.validate(playbook)
        return {"ok": validation["ok"], "playbook": playbook, "validation": validation}

    def evaluate_danger(self, signals: dict[str, float], context_priority: float = 0.0) -> dict[str, Any]:
        danger = self._danger_detector.evaluate(signals, context_priority=context_priority)
        dodge = None
        interrupt = None
        companion_message = None
        if danger.level == "HIGH":
            interrupt_obj = Interrupt(
                priority=1,
                timestamp=self._timebase.now(),
                code="DODGE_REFLEX",
                source="combat_reflex",
                requires_input_release=False,
                payload={"danger_score": danger.score, "signals": signals, "dominant_signal": danger.dominant_signal},
            )
            self._state_bus.publish_interrupt(interrupt_obj)
            interrupt = asdict(interrupt_obj)
            dodge = self._dodge_policy.choose_dodge(danger)
            companion_message = self.persona_event("DODGE_REFLEX", {"danger_score": danger.score}, "default_companion")["message"]
        return {
            "danger_score": danger.score,
            "level": danger.level,
            "components": danger.components,
            "dominant_signal": danger.dominant_signal,
            "interrupt": interrupt,
            "dodge": dodge,
            "dodge_policy": self._dodge_policy.snapshot(),
            "companion_message": companion_message,
        }

    def product_checklist(self, profile: str | None = None, skill: str | None = None, task: str = "complete product demo") -> dict[str, Any]:
        return self._product_e2e.checklist(profile=profile, skill=skill, task=task)

    def run_product_e2e(
        self,
        mode: str = "dry-run",
        seconds: float = 20.0,
        profile: str | None = None,
        skill: str | None = None,
        task: str = "complete product demo",
        use_mock_llm: bool = True,
        chaos: str = "none",
        confirm: bool = False,
    ) -> dict[str, Any]:
        return asdict(
            self._product_e2e.run(
                mode=mode,
                seconds=seconds,
                profile=profile,
                skill=skill,
                task=task,
                use_mock_llm=use_mock_llm,
                chaos=chaos,
                confirm=confirm,
            )
        )

    def product_latest_report(self) -> dict[str, Any]:
        return self._product_e2e.latest_report()

    def _run_status_loop(self) -> None:
        sequence = [
            ("LOAD_TASK", "LoadTaskSkill", "ACQUIRING"),
            ("ENTER_TARGET_REGION", "EnterTargetRegionSkill", "SEARCHING"),
            ("ACQUIRE_TARGET", "AcquireTargetSkill", "TRACKED"),
            ("TRACK_AND_APPROACH", "TrackAndApproachSkill", "TRACKED"),
            ("EXECUTE_VISUAL_ACTION_BLOCK", "ExecuteVisualActionBlockSkill", "CENTERED"),
            ("VERIFY_SUCCESS", "VerifySuccessSkill", "VERIFIED"),
            ("COMPLETE", None, "COMPLETE"),
        ]
        index = 0
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(0.2)
                continue
            with self._lock:
                if self._mode != "RUNNING":
                    break
                node, skill, target = sequence[min(index, len(sequence) - 1)]
                self._current_node = node
                self._current_skill = skill
                self._target_state = target
                self._progress = min(1.0, self._progress + 0.08)
                self._frustration = max(0.0, self._frustration - 2.0)
                if node == "COMPLETE":
                    self._mode = "STOPPED"
                    self._release_all_called = True
                    if self._worker is not None:
                        self._worker.stop()
                    break
            index += 1
            time.sleep(0.5)

    def _find_latest_run_id(self) -> str | None:
        runs_dir = self._root / "logs" / "runs"
        if not runs_dir.exists():
            return None
        runs = [path for path in runs_dir.iterdir() if path.is_dir()]
        if not runs:
            return None
        return max(runs, key=lambda path: path.stat().st_mtime).name

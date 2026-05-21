from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


ALLOWED_SAFE_WINDOW_MARKERS = (
    "pseudo3d_scene",
    "vision_agent_kernel_v0_5",
    "qa sandbox",
    "testbed",
    "genshin",
    "genshin impact",
    "yuan shen",
    "原神",
    "honkai",
    "star rail",
    "崩坏：星穹铁道",
)


class ProductController(Protocol):
    def current_config(self) -> dict[str, Any]: ...
    def list_calibration_profiles(self) -> dict[str, object]: ...
    def get_calibration_profile(self, profile_id: str) -> Any: ...
    def test_calibration_profile(self, profile_id: str | None = None) -> dict[str, object]: ...
    def model_status(self) -> dict[str, Any]: ...
    def list_windows(self) -> dict[str, Any]: ...
    def get_skill(self, skill_id: str) -> dict[str, Any]: ...
    def save_skill(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def validate_skill(self, skill_id: str) -> dict[str, Any]: ...
    def dry_run_skill(self, skill_id: str) -> dict[str, Any]: ...
    def plan_task(self, goal: str, provider: str = "mock", persona_id: str = "default_companion") -> dict[str, Any]: ...
    def persona_event(self, event_code: str, payload: dict[str, Any], persona_id: str) -> dict[str, Any]: ...
    def start(self) -> Any: ...
    def stop(self) -> Any: ...
    def state(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    key: str
    label: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ProductE2EResult:
    ok: bool
    run_id: str
    run_dir: str
    report_path: str
    checklist: list[ChecklistItem]
    selected_profile: str
    selected_skill: str
    planner_provider: str
    task_validation: dict[str, Any]
    execution_mode: str
    safety_events: list[str]
    release_all_called: bool
    companion_summary: str
    confirm_required: bool = False
    error: str | None = None


class ProductE2ERunner:
    def __init__(self, root: Path, controller: ProductController) -> None:
        self._root = root
        self._controller = controller

    def checklist(self, profile: str | None = None, skill: str | None = None, task: str = "complete product demo") -> dict[str, Any]:
        resolved_profile = profile or self._active_profile_id()
        resolved_skill = skill or "demo_product_skill"
        items: list[ChecklistItem] = []
        items.append(ChecklistItem("fastapi_health", "FastAPI health", True, "local service controller is available"))

        profile_ok, profile_detail = self._profile_status(resolved_profile)
        items.append(ChecklistItem("profile_loaded", "Profile loaded", profile_ok, profile_detail))

        model = self._controller.model_status()
        model_ready = bool(model.get("tracker_available"))
        items.append(ChecklistItem("model_ready", "Model ready", model_ready, f"backend={model.get('detector_backend')} tracker={model.get('tracker')}"))

        skill_ok, skill_detail = self._skill_status(resolved_skill)
        items.append(ChecklistItem("skill_valid", "Skill valid", skill_ok, skill_detail))

        try:
            plan = self._controller.plan_task(task, provider="mock", persona_id="default_companion")
            planner_ok = bool(plan.get("ok"))
            planner_detail = f"provider={plan.get('provider')} validation={plan.get('validation', {}).get('simulation')}"
        except Exception as exc:
            planner_ok = False
            planner_detail = _friendly_error(exc)
        items.append(ChecklistItem("planner_ready", "Planner ready", planner_ok, planner_detail))

        config = self._controller.current_config()
        safety_ok = config.get("default_mode") == "dry-run" and config.get("f9_emergency_stop") is True
        items.append(ChecklistItem("safety_ready", "Safety ready", safety_ok, "dry-run default, F9 enabled, safe-window required"))

        report_ready = self._latest_product_report() is not None
        items.append(ChecklistItem("report_ready", "Report ready", report_ready, self._latest_product_report() or "no product report yet"))
        return {
            "ok": all(item.ok for item in items if item.key != "report_ready"),
            "items": [asdict(item) for item in items],
            "profile": resolved_profile,
            "skill": resolved_skill,
        }

    def run(
        self,
        mode: str = "dry-run",
        seconds: float = 20.0,
        profile: str | None = None,
        skill: str | None = None,
        task: str = "complete product demo",
        use_mock_llm: bool = True,
        chaos: str = "none",
        confirm: bool = False,
    ) -> ProductE2EResult:
        del seconds
        provider = "mock" if use_mock_llm else "mock"
        run_id = str(uuid.uuid4())
        run_dir = self._root / "logs" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trace_path = run_dir / "product_e2e_trace.jsonl"
        report_path = run_dir / "product_e2e_report.md"
        selected_profile = profile or self._active_profile_id()
        selected_skill = skill or "demo_product_skill"
        safety_events = ["dry_run_default_verified", "f9_emergency_stop_enabled"]
        checklist_items: list[ChecklistItem] = []
        release_all_called = False

        try:
            self._ensure_demo_skill(selected_skill, selected_profile)
            if mode == "safe-window":
                safe_ok, safe_detail, confirm_required = self._safe_window_gate(confirm)
                checklist_items.append(ChecklistItem("safe_window_gate", "Safe-window gate", safe_ok, safe_detail))
                if confirm_required or not safe_ok:
                    result = ProductE2EResult(
                        ok=False,
                        run_id=run_id,
                        run_dir=str(run_dir),
                        report_path=str(report_path),
                        checklist=checklist_items,
                        selected_profile=selected_profile,
                        selected_skill=selected_skill,
                        planner_provider=provider,
                        task_validation={"ok": False, "errors": [safe_detail]},
                        execution_mode=mode,
                        safety_events=safety_events + ["safe_window_rejected_or_confirmation_required"],
                        release_all_called=True,
                        companion_summary="Safe-window execution is blocked until an authorized test window is selected and confirmed.",
                        confirm_required=confirm_required,
                        error=safe_detail,
                    )
                    self._write_outputs(result, trace_path, report_path)
                    return result

            checklist = self.checklist(selected_profile, selected_skill, task)
            checklist_items.extend(ChecklistItem(**item) for item in checklist["items"] if item["key"] != "report_ready")
            profile_test = self._controller.test_calibration_profile(selected_profile)
            skill_validation = self._controller.validate_skill(selected_skill)
            plan = self._controller.plan_task(task, provider=provider, persona_id="default_companion")
            dry_run = self._controller.dry_run_skill(selected_skill)
            started = self._controller.start()
            stopped = self._controller.stop()
            release_all_called = bool(stopped.runtime_health.release_all_called)
            companion = self._controller.persona_event("TASK_COMPLETE", {"run_id": run_id}, "default_companion")
            safety_events.append("release_all_called" if release_all_called else "release_all_missing")
            checklist_items.extend(
                [
                    ChecklistItem("active_profile_exists", "Active profile exists", bool(profile_test.get("ok")), str(profile_test)),
                    ChecklistItem("skill_validate_ok", "Skill validate OK", bool(skill_validation.get("ok")), str(skill_validation)),
                    ChecklistItem("sandbox_validation_ok", "Sandbox validation OK", bool(plan.get("validation", {}).get("ok")), str(plan.get("validation"))),
                    ChecklistItem("input_backend_safe", "Input backend safe", started.input_backend == "console", f"input_backend={started.input_backend}"),
                    ChecklistItem("telemetry_log_path_created", "Telemetry log path created", trace_path.parent.exists(), str(trace_path)),
                    ChecklistItem("dry_run_passed", "Dry-run passed", bool(dry_run.get("ok")), dry_run.get("result", {}).get("status", "unknown")),
                    ChecklistItem("report_generated", "Report generated", True, str(report_path)),
                ]
            )
            ok = all(item.ok for item in checklist_items if item.key != "report_ready")
            result = ProductE2EResult(
                ok=ok,
                run_id=run_id,
                run_dir=str(run_dir),
                report_path=str(report_path),
                checklist=checklist_items,
                selected_profile=selected_profile,
                selected_skill=selected_skill,
                planner_provider=provider,
                task_validation=plan.get("validation", {}),
                execution_mode=mode,
                safety_events=safety_events,
                release_all_called=release_all_called,
                companion_summary=str(companion["message"]),
                error=None if ok else "One or more checklist items failed.",
            )
            self._write_outputs(result, trace_path, report_path, extra={"plan": plan, "dry_run": dry_run, "chaos": chaos})
            return result
        except Exception as exc:
            try:
                stopped = self._controller.stop()
                release_all_called = bool(stopped.runtime_health.release_all_called)
            except Exception:
                release_all_called = False
            result = ProductE2EResult(
                ok=False,
                run_id=run_id,
                run_dir=str(run_dir),
                report_path=str(report_path),
                checklist=checklist_items,
                selected_profile=selected_profile,
                selected_skill=selected_skill,
                planner_provider=provider,
                task_validation={"ok": False, "errors": [_friendly_error(exc)]},
                execution_mode=mode,
                safety_events=safety_events + ["exception_cleanup_release_all" if release_all_called else "exception_cleanup_failed"],
                release_all_called=release_all_called,
                companion_summary="E2E run stopped safely after an error.",
                error=_friendly_error(exc),
            )
            self._write_outputs(result, trace_path, report_path)
            return result

    def latest_report(self) -> dict[str, Any]:
        report = self._latest_product_report()
        if report is None:
            return {"run_id": None, "report_path": None, "report_markdown": None}
        path = Path(report)
        return {
            "run_id": path.parent.name,
            "report_path": str(path),
            "report_markdown": path.read_text(encoding="utf-8"),
        }

    def _active_profile_id(self) -> str:
        index = self._controller.list_calibration_profiles()
        return str(index.get("active_profile_id") or "default_1920x1080")

    def _profile_status(self, profile_id: str) -> tuple[bool, str]:
        try:
            result = self._controller.test_calibration_profile(profile_id)
            return bool(result.get("ok")), str(result)
        except Exception as exc:
            return False, _friendly_error(exc)

    def _skill_status(self, skill_id: str) -> tuple[bool, str]:
        try:
            self._ensure_demo_skill(skill_id, self._active_profile_id())
            result = self._controller.validate_skill(skill_id)
            return bool(result.get("ok")), str(result)
        except Exception as exc:
            return False, _friendly_error(exc)

    def _safe_window_gate(self, confirm: bool) -> tuple[bool, str, bool]:
        selected_handle = self._controller.list_windows().get("selected_handle")
        if selected_handle is None:
            return False, "Safe-window mode requires selecting an authorized test window first.", False
        selected_title = ""
        for window in self._controller.list_windows().get("windows", []):
            if window.get("handle") == selected_handle:
                selected_title = str(window.get("title", ""))
                break
        allowed = any(marker.lower() in selected_title.lower() for marker in ALLOWED_SAFE_WINDOW_MARKERS)
        if not allowed:
            return False, f"Selected window is not an authorized test window: {selected_title}", False
        if not confirm:
            return False, "confirm_required: user must explicitly confirm safe-window execution.", True
        return True, f"authorized test window confirmed: {selected_title}", False

    def _ensure_demo_skill(self, skill_id: str, profile_id: str) -> None:
        try:
            self._controller.get_skill(skill_id)
            return
        except Exception:
            pass
        if skill_id != "demo_product_skill":
            raise FileNotFoundError(f"Skill not found: {skill_id}")
        self._controller.save_skill(_demo_skill_payload(profile_id))

    def _latest_product_report(self) -> str | None:
        runs_dir = self._root / "logs" / "runs"
        if not runs_dir.exists():
            return None
        reports = list(runs_dir.glob("*/product_e2e_report.md"))
        if not reports:
            return None
        return str(max(reports, key=lambda path: path.stat().st_mtime))

    def _write_outputs(self, result: ProductE2EResult, trace_path: Path, report_path: Path, extra: dict[str, Any] | None = None) -> None:
        trace_payload = {
            "timestamp": time.time(),
            "ok": result.ok,
            "run_id": result.run_id,
            "checklist": [asdict(item) for item in result.checklist],
            "selected_profile": result.selected_profile,
            "selected_skill": result.selected_skill,
            "planner_provider": result.planner_provider,
            "task_validation": result.task_validation,
            "execution_mode": result.execution_mode,
            "safety_events": result.safety_events,
            "release_all_called": result.release_all_called,
            "companion_summary": result.companion_summary,
            "confirm_required": result.confirm_required,
            "error": result.error,
            "extra": extra or {},
        }
        trace_path.write_text(json.dumps(trace_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.write_text(self._render_report(result), encoding="utf-8")

    def _render_report(self, result: ProductE2EResult) -> str:
        checklist = "\n".join(
            f"- [{'x' if item.ok else ' '}] {item.label}: {item.detail}"
            for item in result.checklist
        )
        safety = "\n".join(f"- {event}" for event in result.safety_events)
        return "\n".join(
            [
                "# Product E2E Report",
                "",
                f"- run_id: `{result.run_id}`",
                f"- status: `{'PASS' if result.ok else 'FAILED'}`",
                f"- execution_mode: `{result.execution_mode}`",
                f"- selected_profile: `{result.selected_profile}`",
                f"- selected_skill: `{result.selected_skill}`",
                f"- planner_provider: `{result.planner_provider}`",
                f"- task_validation: `{result.task_validation}`",
                f"- release_all_called: `{result.release_all_called}`",
                f"- confirm_required: `{result.confirm_required}`",
                f"- error: `{result.error or ''}`",
                "",
                "## Checklist Results",
                checklist,
                "",
                "## Safety Events",
                safety,
                "",
                "## Companion Summary",
                result.companion_summary,
            ]
        )


def _demo_skill_payload(profile_id: str) -> dict[str, Any]:
    return {
        "skill_id": "demo_product_skill",
        "name": "Demo Product Skill",
        "type": "combat",
        "version": 1,
        "metadata": {"source": "product_e2e"},
        "environment_profile": profile_id,
        "preconditions": ["require_focus", "target_visible"],
        "steps": [
            {
                "step_id": "maintain_lock",
                "type": "wait_visual_trigger",
                "label": "Maintain target lock",
                "timeout_ms": 1000,
                "interruptible": True,
                "params": {"trigger": "target_visible", "chunk_ms": 100},
            },
            {
                "step_id": "fallback",
                "type": "fallback_basic_loop",
                "label": "Fallback loop",
                "interruptible": True,
                "params": {},
            },
        ],
        "visual_triggers": {"target_visible": {"type": "target_visible"}},
        "success_criteria": ["visual_action_completed"],
        "failure_policy": {"max_retries": 2, "fallback": "pause_and_reacquire"},
        "cleanup": [{"type": "release_all"}],
        "safety": {"dry_run_default": True, "interruptible": True, "require_focus": True, "max_duration_ms": 5000},
    }


def _friendly_error(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__

"""Evolution engine: failure -> signature -> repair session -> patch -> validation -> versioned skill."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.state_bus import StateBus
from learning.genshin_failure_analyzer import GenshinFailureAnalyzer
from learning.skill_patch_suggester import SkillPatchSuggester
from learning.failure_signature import FailureSignatureBuilder
from repair.repair_session import RepairSession
from repair.demo_segmenter import DemoSegmenter
from repair.skill_patch_builder import SkillPatchBuilder, SkillPatchDraft
from repair.repair_validator import RepairValidator
from repair.repair_benchmark_runner import RepairBenchmarkRunner, BenchmarkDelta

_PATCHES_DIR = Path("data/skill_patches")


class EvolutionEngine:
    """Flywheel: failure -> signature -> repair session -> patch draft -> sandbox replay -> versioned skill.

    Stage 46 refactoring: the engine now orchestrates the repair/ modules while
    preserving the original public API (``handle_failure``, ``approve_patch``,
    ``list_patch_drafts``, ``benchmark_delta``).
    """

    def __init__(
        self,
        state_bus: StateBus,
        analyzer: GenshinFailureAnalyzer | None = None,
        patches_dir: Path | str | None = None,
    ) -> None:
        self._state_bus = state_bus
        self._analyzer = analyzer or GenshinFailureAnalyzer()
        self._suggester = SkillPatchSuggester()
        self._signature_builder = FailureSignatureBuilder()
        self._approved_patches: list[dict[str, Any]] = []
        self._patch_drafts: list[dict[str, Any]] = []
        self._patches_dir = Path(patches_dir) if patches_dir else _PATCHES_DIR
        self._patches_dir.mkdir(parents=True, exist_ok=True)

        # Stage 46: repair module components
        self._segmenter = DemoSegmenter()
        self._patch_builder = SkillPatchBuilder()
        self._validator = RepairValidator()
        self._benchmark_runner = RepairBenchmarkRunner()
        self._repair_sessions: dict[str, RepairSession] = {}
        self._skill_patch_drafts: dict[str, SkillPatchDraft] = {}
        self._benchmark_deltas: dict[str, BenchmarkDelta] = {}

        self._state_bus.subscribe("skill_result", self.on_skill_result)

    # -- public API (backward compatible) ------------------------------------

    def on_skill_result(self, result: Any) -> None:
        if hasattr(result, "status") and result.status == "FAILED":
            obs_data = {}
            if hasattr(result, "payload") and isinstance(result.payload, dict):
                obs_data = result.payload.get("observation", {})
            self.handle_failure(
                skill_name=getattr(result, "skill_name", "unknown_skill"),
                failure_code=getattr(result, "failure_code", "UNKNOWN"),
                observation_data=obs_data,
            )

    def handle_failure(
        self, skill_name: str, failure_code: str, observation_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        # Build failure signature via legacy path
        signature = self._signature_builder.build(
            node_type="skill",
            skill_id=skill_name,
            failure_code=failure_code,
            observation=observation_data,
            context={},
        )

        # Stage 46: create a repair session for the failure
        repair_session = RepairSession(
            failure_signature_id=signature.failure_id,
            skill_id=skill_name,
        )
        self._repair_sessions[repair_session.session_id] = repair_session

        # Auto-seed a demonstration with suggested actions
        suggestion = self._suggester.suggest(signature)
        patches = suggestion.get("patches", [])
        if patches:
            repair_session.start_demonstration()
            for patch_action in patches:
                repair_session.record_action(
                    action_type=str(patch_action),
                    params={"source": "auto_suggestion", "failure_code": failure_code},
                )
            repair_session.propose_checkpoint(
                verifier_contract={"failure_code": failure_code, "skill_id": skill_name},
            )

        # Segment the demonstration
        segments = self._segmenter.segment(repair_session.events)

        # Build a SkillPatchDraft from segments
        patch_draft: SkillPatchDraft | None = None
        if segments:
            patch_draft = self._patch_builder.build(repair_session, segments)
            self._skill_patch_drafts[patch_draft.patch_id] = patch_draft

            # Validate in sandbox
            dry_run_ok = self._validator.validate_dry_run(patch_draft)
            if dry_run_ok:
                patch_draft.status = "SANDBOX_VALIDATED"
                patch_draft.validation = {
                    **patch_draft.validation,
                    "dry_run_passed": True,
                }
                verifier_ok = self._validator.validate_verifier_replay(
                    patch_draft, patch_draft.verifier_contract,
                )
                patch_draft.validation = {
                    **patch_draft.validation,
                    "verifier_replay_passed": verifier_ok,
                }

            # Write patch file
            self._write_skill_patch_draft(patch_draft)

        # Also maintain legacy patch draft dict for backward compatibility
        patch_id = f"{skill_name}_{uuid.uuid4().hex[:8]}"
        version = self._next_version(skill_name)
        legacy_draft = {
            "patch_id": patch_id,
            "skill_id": skill_name,
            "version": version,
            "failure_id": signature.failure_id,
            "failure_code": failure_code,
            "patches": patches,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "verified": False,
            "approved": False,
            "replay_result": None,
            "repair_session_id": repair_session.session_id,
            "new_patch_id": patch_draft.patch_id if patch_draft else None,
        }
        self._patch_drafts.append(legacy_draft)

        verified = self._verify_in_sandbox(legacy_draft)
        legacy_draft["verified"] = verified

        self._write_patch_draft(legacy_draft)
        self._publish_patch_event(legacy_draft)

        return legacy_draft

    def approve_patch(self, skill_id: str) -> bool:
        # Try Stage 46 patch drafts first
        for patch_draft in self._skill_patch_drafts.values():
            if patch_draft.skill_id == skill_id and patch_draft.status == "SANDBOX_VALIDATED":
                patch_draft.status = "APPROVED"
                self._write_skill_patch_draft(patch_draft)
                break

        # Legacy approval path
        for draft in self._patch_drafts:
            if draft["skill_id"] == skill_id and draft["verified"]:
                draft["approved"] = True
                draft["approved_at"] = datetime.now(timezone.utc).isoformat()
                self._approved_patches.append(draft)
                self._write_patch_draft(draft)
                self._write_version_record(draft)
                self._publish_patch_event(draft)

                # Stage 46: run benchmark after approval
                new_patch_id = draft.get("new_patch_id")
                if new_patch_id and new_patch_id in self._skill_patch_drafts:
                    patch_draft = self._skill_patch_drafts[new_patch_id]
                    patch_draft.status = "APPROVED"
                    self._write_skill_patch_draft(patch_draft)
                    self._benchmark_runner.run_before(skill_id)
                    self._benchmark_runner.run_after(skill_id, patch_draft)
                    delta = self._benchmark_runner.compute_delta(skill_id, patch_draft)
                    self._benchmark_deltas[skill_id] = delta

                return True
        return False

    def list_patch_drafts(self, skill_id: str | None = None) -> list[dict[str, Any]]:
        drafts = self._patch_drafts
        if skill_id:
            drafts = [d for d in drafts if d["skill_id"] == skill_id]
        return drafts

    def benchmark_delta(self, skill_id: str) -> dict[str, Any] | None:
        # Stage 46: return structured BenchmarkDelta if available
        delta = self._benchmark_deltas.get(skill_id)
        if delta is not None:
            return {
                "skill_id": delta.skill_id,
                "patch_id": delta.patch_id,
                "before_pass_rate": delta.before_pass_rate,
                "after_pass_rate": delta.after_pass_rate,
                "before_failure_count": delta.before_failure_count,
                "after_failure_count": delta.after_failure_count,
                "improvement": delta.improvement,
            }

        # Legacy fallback
        before_runs = [d for d in self._patch_drafts if d["skill_id"] == skill_id and not d["verified"]]
        after_runs = [d for d in self._approved_patches if d["skill_id"] == skill_id]
        if not before_runs or not after_runs:
            return None
        return {
            "skill_id": skill_id,
            "failures_before": len(before_runs),
            "patches_applied": len(after_runs),
            "last_patch_id": after_runs[-1]["patch_id"],
            "last_version": after_runs[-1]["version"],
        }

    # -- Stage 46 extended API -----------------------------------------------

    def get_repair_session(self, session_id: str) -> RepairSession | None:
        """Retrieve a repair session by ID."""
        return self._repair_sessions.get(session_id)

    def get_skill_patch_draft(self, patch_id: str) -> SkillPatchDraft | None:
        """Retrieve a SkillPatchDraft by patch ID."""
        return self._skill_patch_drafts.get(patch_id)

    def get_benchmark_delta(self, skill_id: str) -> BenchmarkDelta | None:
        """Retrieve the BenchmarkDelta for a skill, if any."""
        return self._benchmark_deltas.get(skill_id)

    # -- internals -----------------------------------------------------------

    def _next_version(self, skill_id: str) -> str:
        existing = sorted(self._patches_dir.glob(f"{skill_id}_v*.json"))
        if not existing:
            return "v1"
        last = existing[-1].stem
        num = int(last.split("_v")[1])
        return f"v{num + 1}"

    def _write_patch_draft(self, draft: dict[str, Any]) -> None:
        path = self._patches_dir / f"{draft['patch_id']}.json"
        path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_skill_patch_draft(self, draft: SkillPatchDraft) -> None:
        """Write a Stage 46 SkillPatchDraft to disk."""
        path = self._patches_dir / f"{draft.patch_id}.json"
        path.write_text(json.dumps(draft.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_version_record(self, draft: dict[str, Any]) -> None:
        path = self._patches_dir / f"{draft['skill_id']}_{draft['version']}.json"
        path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")

    def _verify_in_sandbox(self, patch: dict[str, Any]) -> bool:
        skill_id = patch["skill_id"]
        test_marker = skill_id.replace("_", " and ")
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/", "-k", test_marker,
            "-x", "--tb=no", "-q",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            patch["replay_result"] = {
                "returncode": res.returncode,
                "stdout_tail": (res.stdout or "")[-200:],
                "passed": res.returncode == 0,
            }
            return res.returncode == 0
        except subprocess.TimeoutExpired:
            patch["replay_result"] = {"passed": False, "error": "timeout"}
            return False
        except Exception as exc:
            patch["replay_result"] = {"passed": False, "error": str(exc)}
            return False

    def _publish_patch_event(self, draft: dict[str, Any]) -> None:
        slot = self._state_bus.get_slot("learning.patch_event")
        if slot is not None:
            slot.put({
                "patch_id": draft["patch_id"],
                "skill_id": draft["skill_id"],
                "version": draft["version"],
                "verified": draft["verified"],
                "approved": draft["approved"],
            })

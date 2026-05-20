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

_PATCHES_DIR = Path("data/skill_patches")


class EvolutionEngine:
    """Flywheel: failure → signature → patch draft → sandbox replay → versioned skill."""

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

        self._state_bus.subscribe("skill_result", self.on_skill_result)

    # -- public API ----------------------------------------------------------

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
        signature = self._signature_builder.build(
            node_type="skill",
            skill_id=skill_name,
            failure_code=failure_code,
            observation=observation_data,
            context={},
        )
        suggestion = self._suggester.suggest(signature)

        patch_id = f"{skill_name}_{uuid.uuid4().hex[:8]}"
        version = self._next_version(skill_name)
        patch_draft = {
            "patch_id": patch_id,
            "skill_id": skill_name,
            "version": version,
            "failure_id": signature.failure_id,
            "failure_code": failure_code,
            "patches": suggestion.get("patches", []),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "verified": False,
            "approved": False,
            "replay_result": None,
        }
        self._patch_drafts.append(patch_draft)

        verified = self._verify_in_sandbox(patch_draft)
        patch_draft["verified"] = verified

        self._write_patch_draft(patch_draft)
        self._publish_patch_event(patch_draft)

        return patch_draft

    def approve_patch(self, skill_id: str) -> bool:
        for draft in self._patch_drafts:
            if draft["skill_id"] == skill_id and draft["verified"]:
                draft["approved"] = True
                draft["approved_at"] = datetime.now(timezone.utc).isoformat()
                self._approved_patches.append(draft)
                self._write_patch_draft(draft)
                self._write_version_record(draft)
                self._publish_patch_event(draft)
                return True
        return False

    def list_patch_drafts(self, skill_id: str | None = None) -> list[dict[str, Any]]:
        drafts = self._patch_drafts
        if skill_id:
            drafts = [d for d in drafts if d["skill_id"] == skill_id]
        return drafts

    def benchmark_delta(self, skill_id: str) -> dict[str, Any] | None:
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

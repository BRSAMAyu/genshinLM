from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    task_completion_rate: float
    skill_success_rate: float
    verifier_accuracy: float
    target_lost_count: int
    recovery_success_rate: float
    combat_survival_time: float
    collect_success_rate: float
    user_intervention_count: int
    mean_time_to_complete: float


class BenchmarkSuite:
    def load_runs(self, runs_root: Path) -> list[dict]:
        runs: list[dict] = []
        if not runs_root.exists():
            return runs
        for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
            runs.append(self._load_run(run_dir))
        return runs

    def summarize_run_folder(self, runs_root: Path) -> dict:
        return self.summarize(self.load_runs(runs_root))

    def summarize(self, runs: list[dict]) -> dict:
        if not runs:
            return asdict(BenchmarkMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0))
        completed = sum(1 for run in runs if run.get("final_outcome") == "COMPLETE")
        skill_success = sum(float(run.get("skill_success_rate", 0.0)) for run in runs) / len(runs)
        return asdict(
            BenchmarkMetrics(
                completed / len(runs),
                skill_success,
                sum(float(run.get("verifier_accuracy", 1.0)) for run in runs) / len(runs),
                sum(int(run.get("target_lost_count", 0)) for run in runs),
                sum(float(run.get("recovery_success_rate", 1.0)) for run in runs) / len(runs),
                max(float(run.get("combat_survival_time", 0.0)) for run in runs),
                sum(float(run.get("collect_success_rate", 0.0)) for run in runs) / len(runs),
                sum(int(run.get("user_intervention_count", 0)) for run in runs),
                sum(float(run.get("duration_sec", 0.0)) for run in runs) / len(runs),
            )
        )

    def _load_run(self, run_dir: Path) -> dict:
        records = []
        for path in run_dir.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        report = self._read_json(run_dir / "health_report.json")
        final_outcome = "COMPLETE" if any(
            record.get("to") == "COMPLETE"
            or record.get("current_node") == "COMPLETE"
            or record.get("final_state") == "COMPLETE"
            or record.get("event") == "task_complete"
            for record in records
        ) else report.get("final_outcome", "UNKNOWN")
        skill_records = [record for record in records if "skill_result" in record or record.get("event") in {"skill_result", "combo_step_success"}]
        skill_success = sum(1 for record in skill_records if record.get("status") in {None, "SUCCESS"} or record.get("skill_result", {}).get("status") == "SUCCESS")
        verifier_records = [record for record in records if "verifier" in record or "verifier_result" in record]
        verifier_ok = sum(1 for record in verifier_records if record.get("ok") is True or record.get("verifier_result", {}).get("ok") is True)
        recoveries = [record for record in records if "RECOVER" in str(record)]
        return {
            "run_id": run_dir.name,
            "final_outcome": final_outcome,
            "skill_success_rate": skill_success / len(skill_records) if skill_records else float(final_outcome == "COMPLETE"),
            "verifier_accuracy": verifier_ok / len(verifier_records) if verifier_records else 1.0,
            "target_lost_count": sum(1 for record in records if "TARGET_LOST" in str(record)),
            "recovery_success_rate": 1.0 if recoveries else 0.0,
            "combat_survival_time": float(report.get("combat_survival_time", 0.0)),
            "collect_success_rate": 1.0 if any("collection" in str(record).lower() and "SUCCESS" in str(record) for record in records) else 0.0,
            "user_intervention_count": sum(1 for record in records if "HUMAN" in str(record) or "user_intervention" in str(record)),
            "duration_sec": float(report.get("duration_sec", 0.0)),
        }

    def _read_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

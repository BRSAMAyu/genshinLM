from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "logs" / "runs"


def _latest_run() -> Path:
    runs = [path for path in RUNS.iterdir() if path.is_dir()]
    if not runs:
        raise RuntimeError("no logs/runs entries found")
    return max(runs, key=lambda path: path.stat().st_mtime)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _numeric(records: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for record in records:
        payload = record.get("payload", record)
        value = payload
        for part in key.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a markdown report from demo telemetry.")
    parser.add_argument("--run-id")
    parser.add_argument("--latest", action="store_true")
    args = parser.parse_args()
    run_dir = _latest_run() if args.latest or not args.run_id else RUNS / args.run_id
    health_path = run_dir / "health_report.json"
    health = json.loads(health_path.read_text(encoding="utf-8")) if health_path.exists() else {}
    records: list[dict[str, Any]] = []
    for name in [
        "task_demo_trace.jsonl",
        "endurance_trace.jsonl",
        "servo_trace.jsonl",
        "chaos_recovery_trace.jsonl",
        "obstacle_recovery_trace.jsonl",
    ]:
        records.extend(_read_jsonl(run_dir / name))
    transitions = [
        record for record in records
        if record.get("event") == "state_transition" or record.get("event_type") == "state_transition"
    ]
    interrupts = [
        record for record in records
        if record.get("event") == "interrupt" or record.get("event_type") == "interrupt"
    ]
    frustration = _numeric(records, "progress.frustration") + _numeric(records, "payload.progress.frustration")
    tracking_centers = _numeric(records, "payload.center_error_px.0")
    report_path = run_dir / "demo_report.md"
    lines = [
        "# Vision Agent MVP Demo Report",
        "",
        f"- run_dir: `{run_dir}`",
        f"- records: {len(records)}",
        f"- release_all_called: {health.get('release_all_called', 'unknown')}",
        f"- telemetry_drops: {health.get('dropped_low_priority_logs', 0)}",
        "",
        "## Runtime Health",
        "",
        f"- max_memory_mb: {health.get('max_memory_mb', 'n/a')}",
        f"- memory_growth_mb: {health.get('memory_growth_mb', 'n/a')}",
        f"- avg_perception_fps: {health.get('avg_perception_fps', 'n/a')}",
        f"- avg_controller_fps: {health.get('avg_controller_fps', 'n/a')}",
        f"- max_telemetry_backlog: {health.get('max_telemetry_backlog', 'n/a')}",
        "",
        "## State Transitions",
        "",
    ]
    if transitions:
        for transition in transitions[:50]:
            if "previous_state" in transition:
                lines.append(f"- {transition.get('previous_state')} -> {transition.get('next_state')}: {transition.get('reason')}")
            else:
                payload = transition.get("payload", {})
                lines.append(f"- {payload.get('previous_state')} -> {payload.get('next_state')}: {payload.get('reason')}")
    else:
        lines.append("- none recorded")
    lines.extend(["", "## Tracking Stats", ""])
    if tracking_centers:
        lines.append(f"- center_error_x_avg: {statistics.mean(tracking_centers):.3f}")
        lines.append(f"- center_error_x_max_abs: {max(abs(value) for value in tracking_centers):.3f}")
    else:
        lines.append("- no center error series found")
    lines.extend(["", "## Progress / Frustration", ""])
    if frustration:
        lines.append(f"- frustration_avg: {statistics.mean(frustration):.3f}")
        lines.append(f"- frustration_max: {max(frustration):.3f}")
    else:
        lines.append("- no frustration series found")
    lines.extend(["", "## Interrupts", ""])
    if interrupts:
        for interrupt in interrupts[:50]:
            payload = interrupt.get("payload", interrupt)
            lines.append(f"- {payload.get('code')} priority={payload.get('priority')} source={payload.get('source')}")
    else:
        lines.append("- none recorded")
    lines.extend(["", "## Failures", "", "- inspect trace files for skill_result failure_code entries."])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[demo_report] report_path={report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

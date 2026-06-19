"""Replayable trace recording (JSONL).

A failed run must be reproducible without the live session so a fix-agent (or a
human) can replay exactly what happened. Each scenario's trace is one JSONL file:
a header line (scenario + result), then one line per step.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from harness.core import Scenario, ScenarioResult, StepRecord


class TraceRecorder:
    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def record(
        self, scenario: Scenario, trace: list[StepRecord], result: ScenarioResult,
    ) -> str:
        path = self._dir / f"{scenario.scenario_id}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "header", "scenario": asdict(scenario),
                                 "result": asdict(result)}) + "\n")
            for rec in trace:
                fh.write(json.dumps({"type": "step", **asdict(rec)}) + "\n")
        return str(path)


def read_trace(path: str | Path) -> tuple[dict, list[dict]]:
    """Return (header, steps) from a recorded trace file."""
    header: dict = {}
    steps: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "header":
                header = obj
            elif obj.get("type") == "step":
                steps.append(obj)
    return header, steps

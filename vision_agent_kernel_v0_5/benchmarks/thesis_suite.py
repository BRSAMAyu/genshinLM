from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.autonomous_task_brain import AutonomousTaskBrain, TaskBrainConfig
from planning.screen_state_claim import ScreenStateClaim
from runtime.claim_runtime import ReliabilityStore

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BenchmarkRunResult:
    baseline_name: str
    success_rate: float
    avg_duration_sec: float
    estimated_token_cost: int
    human_interventions: int
    skills_induced: int
    simulated: bool = True
    evidence_level: str = "synthetic_model"


class ThesisSuiteRunner:
    """Runs comparative evaluation benchmarks for the verifier-first visual runtime.

    Compares:
    1. Pure VLM Direct Controller (zero reuse, high token cost)
    2. Pure Scripted Macro (fragile, zero adaptability)
    3. Aurora Unified (Ours - Skill Applicability Gate + Skill Induction Gate)
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or Path("benchmark_reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_comparative_benchmark(self, quest_name: str, trials: int = 5) -> list[BenchmarkRunResult]:
        """Run a deterministic synthetic benchmark model for thesis planning.

        This suite is intentionally not a real-world evidence claim. It exists
        to keep the paper metric schema, reports, and comparison axes stable
        before real testbed/client traces are available. Reports are marked as
        synthetic so they cannot be mistaken for measured completion rates.
        """
        log.info("[ThesisSuite] Starting synthetic comparative benchmark for quest: %s across %d trials", quest_name, trials)
        trials = max(1, trials)
        results = []

        # 1. Evaluate Baseline 1: Pure VLM Direct Controller
        results.append(
            BenchmarkRunResult(
                baseline_name="Pure VLM Direct Controller",
                success_rate=_bounded_mean([0.70, 0.75, 0.80], trials),
                avg_duration_sec=45.2,
                estimated_token_cost=84000 * trials,
                human_interventions=max(1, round(0.6 * trials)),
                skills_induced=0,
            )
        )

        # 2. Evaluate Baseline 2: Pure Scripted Macro
        results.append(
            BenchmarkRunResult(
                baseline_name="Pure Scripted Macro",
                success_rate=_bounded_mean([0.35, 0.40, 0.45], trials),
                avg_duration_sec=12.5,
                estimated_token_cost=0,
                human_interventions=max(1, round(1.2 * trials)),
                skills_induced=0,
            )
        )

        # 3. Evaluate Aurora Unified (Ours)
        # Synthetic dynamic reuse model: first trial is slow exploration, later
        # trials reuse induced skills. Replace this with trace-backed metrics
        # before using the suite for a paper claim.
        aurora_durations = [42.0] + [9.0 for _ in range(max(0, trials - 1))]
        aurora_tokens = [38000] + [2500 for _ in range(max(0, trials - 1))]
        results.append(
            BenchmarkRunResult(
                baseline_name="Aurora Unified (Ours)",
                success_rate=_bounded_mean([0.85, 0.90, 0.95], trials),
                avg_duration_sec=sum(aurora_durations) / len(aurora_durations),
                estimated_token_cost=sum(aurora_tokens),
                human_interventions=1 if trials > 1 else 0,
                skills_induced=1 if trials > 1 else 0,
            )
        )

        self._generate_report(quest_name, results)
        return results

    def _generate_report(self, quest_name: str, results: list[BenchmarkRunResult]) -> None:
        report_path = self.output_dir / f"thesis_benchmark_{quest_name.lower().replace(' ', '_')}.md"
        
        md = []
        md.append(f"# Thesis Evaluation Report: {quest_name}")
        md.append(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        md.append("> Evidence level: synthetic planning model. Do not cite these numbers as real-world results until replaced by trace-backed AuroraBench runs.\n")
        md.append("## 1. Executive Summary")
        md.append("This report defines the comparative metric schema for evaluating whether **Aurora Unified** reduces VLM API dependencies and latency via verifier-first hierarchical skill induction. Current values are synthetic placeholders for pipeline validation.\n")
        
        md.append("## 2. Quantitative Performance Metrics")
        md.append("| Baseline Model | Evidence | Success Rate (SR) | Avg Duration (sec) | Token Cost (tokens) | Human Interventions | Induced Skills |")
        md.append("|---|---|---|---|---|---|---|")
        for r in results:
            md.append(f"| {r.baseline_name} | {r.evidence_level} | {r.success_rate:.0%} | {r.avg_duration_sec:.1f}s | {r.estimated_token_cost:,} | {r.human_interventions} | {r.skills_induced} |")
        
        md.append("\n## 3. Scientific Findings")
        md.append("* **Decoupled Strategic Brain:** By separating tactical planning from motor execution, the VLM serves as a slow-loop explorer, while local skills act as high-frequency fast control.")
        md.append("* **Token Cost Hypothesis:** Aurora should reduce token cost after first success if traces compile into verified reusable skills.")
        md.append("* **Adaptability Hypothesis:** Aurora should outperform scripted macros when quest state shifts or blocked paths require replanning.")
        md.append("\n## 4. Real Evidence Required Before Publication")
        md.append("* Replace synthetic success rates with AuroraBench trace-backed runs.")
        md.append("* Attach ClaimGraph, EvidenceGraph, and Skill promotion artifacts for every task.")
        md.append("* Report confidence intervals and failure categories, not only averages.")

        report_path.write_text("\n".join(md), encoding="utf-8")
        log.info("[ThesisSuite] Report successfully generated at: %s", report_path)


def _bounded_mean(values: list[float], trials: int) -> float:
    repeated = [values[min(i, len(values) - 1)] for i in range(trials)]
    return sum(repeated) / len(repeated)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    runner = ThesisSuiteRunner()
    runner.run_comparative_benchmark("Genshin Opening Storyline")

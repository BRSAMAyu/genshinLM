"""Report builder: produces JSON and Markdown benchmark reports."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from benchmarks.benchmark_types import BenchmarkReport, BenchmarkResult


class ReportBuilder:
    """Builds JSON and Markdown reports from benchmark results."""

    def __init__(self, output_dir: str = "benchmark_reports") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # -- public API ---------------------------------------------------------

    def build_json_report(self, report: BenchmarkReport) -> Path:
        """Write a full JSON report file and return its path."""
        path = self._output_dir / f"{report.suite_name}_{report.run_id}_report.json"
        data = self._serialize_report(report)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def build_markdown_report(self, report: BenchmarkReport) -> Path:
        """Write a Markdown summary report file and return its path."""
        path = self._output_dir / f"{report.suite_name}_{report.run_id}_report.md"
        md = self._render_markdown(report)
        path.write_text(md, encoding="utf-8")
        return path

    def build_all(self, report: BenchmarkReport) -> tuple[Path, Path]:
        """Build both JSON and Markdown reports. Returns (json_path, md_path)."""
        json_path = self.build_json_report(report)
        md_path = self.build_markdown_report(report)
        return json_path, md_path

    # -- serialization ------------------------------------------------------

    def _serialize_report(self, report: BenchmarkReport) -> dict[str, Any]:
        """Convert a BenchmarkReport into a JSON-serializable dict."""
        results_data: list[dict[str, Any]] = []
        for r in report.results:
            results_data.append(self._serialize_result(r))

        return {
            "suite_name": report.suite_name,
            "run_id": report.run_id,
            "timestamp": report.timestamp,
            "total_scenarios": report.total_scenarios,
            "passed_scenarios": report.passed_scenarios,
            "failed_scenarios": report.failed_scenarios,
            "evidence_coverage_rate": report.evidence_coverage_rate,
            "results": results_data,
            "summary": report.summary,
        }

    def _serialize_result(self, result: BenchmarkResult) -> dict[str, Any]:
        """Convert a single BenchmarkResult into a JSON-serializable dict."""
        return {
            "benchmark_id": result.benchmark_id,
            "run_id": result.run_id,
            "suite_name": result.suite_name,
            "scenario_name": result.scenario_name,
            "passed": result.passed,
            "evidence_ids": result.evidence_ids,
            "report": result.report,
            "metrics": asdict(result.metrics),
        }

    # -- markdown rendering -------------------------------------------------

    def _render_markdown(self, report: BenchmarkReport) -> str:
        """Render a Markdown summary for the report."""
        lines: list[str] = []
        lines.append(f"# Benchmark Report: {report.suite_name}")
        lines.append("")
        lines.append(f"- **Run ID**: {report.run_id}")
        lines.append(f"- **Timestamp**: {report.timestamp}")
        lines.append(f"- **Total Scenarios**: {report.total_scenarios}")
        lines.append(f"- **Passed**: {report.passed_scenarios}")
        lines.append(f"- **Failed**: {report.failed_scenarios}")
        lines.append(f"- **Evidence Coverage Rate**: {report.evidence_coverage_rate:.2%}")
        lines.append("")

        # Summary table
        lines.append("## Scenario Results")
        lines.append("")
        lines.append("| Scenario | Passed | Evidence Count |")
        lines.append("|----------|--------|---------------|")
        for r in report.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"| {r.scenario_name} | {status} | {len(r.evidence_ids)} |")
        lines.append("")

        # Evidence coverage section
        lines.append("## Evidence Coverage")
        lines.append("")
        for r in report.results:
            lines.append(f"### {r.scenario_name}")
            lines.append(f"- Coverage: {r.metrics.evidence_coverage:.2%}")
            if r.evidence_ids:
                lines.append(f"- Evidence IDs: {', '.join(r.evidence_ids[:10])}")
                if len(r.evidence_ids) > 10:
                    lines.append(f"  ... and {len(r.evidence_ids) - 10} more")
            lines.append("")

        # Verifier / interrupt / recovery / safety summary from report dicts
        lines.append("## Detailed Metrics")
        lines.append("")
        for r in report.results:
            lines.append(f"### {r.scenario_name}")
            m = r.metrics
            lines.append(f"- frame_to_observation_ms: {m.frame_to_observation_ms:.3f}")
            lines.append(f"- observation_to_interrupt_ms: {m.observation_to_interrupt_ms:.3f}")
            lines.append(f"- interrupt_to_lease_ms: {m.interrupt_to_lease_ms:.3f}")
            lines.append(f"- danger_clear_time_ms: {m.danger_clear_time_ms:.3f}")
            lines.append(f"- danger_false_clear_rate: {m.danger_false_clear_rate:.3f}")
            lines.append(f"- resume_success_rate: {m.resume_success_rate:.3f}")
            lines.append(f"- max_consecutive_dodges: {m.max_consecutive_dodges}")
            lines.append(f"- final_task_success: {m.final_task_success}")
            if m.boss_clear_rate or "boss_clear_rate" in r.report:
                lines.append(f"- boss_clear_rate: {m.boss_clear_rate:.3f}")
                lines.append(f"- survival_rate: {m.survival_rate:.3f}")
                lines.append(f"- target_reacquire_success_rate: {m.target_reacquire_success_rate:.3f}")
                lines.append(f"- heal_success_rate: {m.heal_success_rate:.3f}")
                lines.append(f"- safe_abort_success_rate: {m.safe_abort_success_rate:.3f}")
            # Include benchmark-specific report keys
            if r.report:
                lines.append("")
                lines.append("**Report Details:**")
                for key, value in r.report.items():
                    lines.append(f"- {key}: {value}")
            lines.append("")

        # Safety summary (check for safety-related keys in reports)
        safety_lines = self._extract_safety_summary(report)
        if safety_lines:
            lines.append("## Safety Summary")
            lines.append("")
            for sl in safety_lines:
                lines.append(sl)
            lines.append("")

        return "\n".join(lines)

    def _extract_safety_summary(self, report: BenchmarkReport) -> list[str]:
        """Extract safety-related entries from result reports."""
        lines: list[str] = []
        for r in report.results:
            if "safety_blocks" in r.report:
                lines.append(f"- **{r.scenario_name}** safety blocks: {r.report['safety_blocks']}")
            if "interrupt_count" in r.report:
                lines.append(f"- **{r.scenario_name}** interrupts: {r.report['interrupt_count']}")
            if "recovery_transitions" in r.report:
                lines.append(f"- **{r.scenario_name}** recoveries: {r.report['recovery_transitions']}")
            if "blocked_actions" in r.report:
                lines.append(f"- **{r.scenario_name}** blocked: {r.report['blocked_actions']}")
            if "verifier_results" in r.report:
                lines.append(f"- **{r.scenario_name}** verifier: {r.report['verifier_results']}")
        return lines

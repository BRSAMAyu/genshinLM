#!/usr/bin/env python3
"""AuroraBench: run benchmark suites for the Aurora Vision Agent Kernel.

Usage:
    python scripts/run_aurorabench.py --suite [all|reflex|long_horizon|repair|ui_safety] --mode [dry-run|live] --output-dir DIR
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.benchmark_types import BenchmarkSuiteConfig
from benchmarks.benchmark_runner import BenchmarkRunner
from benchmarks.report_builder import ReportBuilder


def _register_suites(runner: BenchmarkRunner) -> None:
    """Register all available benchmark suites with the runner."""
    # Reflex gauntlet
    from benchmarks.reflex_gauntlet.evaluator import ReflexGauntletEvaluator
    runner.register_suite("reflex", lambda: ReflexGauntletEvaluator().run_all())

    # Long-horizon route/fight/collect/resume
    from benchmarks.long_horizon_route_fight_collect_resume.runner import run_all_long_horizon
    runner.register_suite("long_horizon", run_all_long_horizon)

    # Failure-to-skill-repair
    from benchmarks.failure_to_skill_repair.runner import run_all_repair
    runner.register_suite("repair", run_all_repair)

    # High-res UI safety grounding
    from benchmarks.high_res_ui_safety_grounding.runner import run_all_ui_safety
    runner.register_suite("ui_safety", run_all_ui_safety)


def main() -> int:
    parser = argparse.ArgumentParser(description="AuroraBench: run benchmark suites")
    parser.add_argument(
        "--suite",
        choices=["all", "reflex", "long_horizon", "repair", "ui_safety"],
        default="all",
        help="Which suite to run (default: all)",
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "live"],
        default="dry-run",
        help="Run mode (default: dry-run)",
    )
    parser.add_argument(
        "--output-dir",
        default="benchmark_reports",
        help="Directory for report output (default: benchmark_reports)",
    )
    args = parser.parse_args()

    dry_run = args.mode == "dry-run"
    config = BenchmarkSuiteConfig(
        suite_name=args.suite,
        dry_run=dry_run,
        output_dir=args.output_dir,
    )

    runner = BenchmarkRunner(config=config)
    _register_suites(runner)

    print(f"AuroraBench | suite={args.suite} | mode={args.mode} | output={args.output_dir}")
    print(f"Registered suites: {runner.registered_suites()}")
    print()

    # Run suites
    all_pass = True

    if args.suite == "all":
        reports = runner.run_all()
    else:
        reports = [runner.run_suite(args.suite)]

    # Build Markdown reports and print summary
    builder = ReportBuilder(output_dir=args.output_dir)

    for report in reports:
        json_path, md_path = builder.build_all(report)
        status = "PASS" if report.failed_scenarios == 0 else "FAIL"
        print(f"[{status}] {report.suite_name}: {report.passed_scenarios}/{report.total_scenarios} passed | evidence_coverage={report.evidence_coverage_rate:.2%}")
        if report.failed_scenarios > 0:
            all_pass = False
            for r in report.results:
                if not r.passed:
                    print(f"  FAIL: {r.scenario_name}")
        print(f"  JSON: {json_path}")
        print(f"  MD:   {md_path}")
        print()

    overall = "ALL PASS" if all_pass else "SOME FAILED"
    print(f"AuroraBench complete: {overall}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

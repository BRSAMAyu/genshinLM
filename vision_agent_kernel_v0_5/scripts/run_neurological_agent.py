#!/usr/bin/env python3
"""Run the L0-L9 neurological AgentLoop with live Genshin gameplay.

Usage (dry-run, no game needed):
    python scripts/run_neurological_agent.py --goal "观察周围环境" --dry-run

Usage (live, Genshin must be running and window focused):
    python scripts/run_neurological_agent.py --goal "观察周围环境" --window-title "原神"
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import threading

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("NeurologicalAgent")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sparkle Neurological Agent (L0-L9)")
    parser.add_argument("--goal", required=True, help="Natural language goal")
    parser.add_argument("--window-title", default="原神", help="Game window title")
    parser.add_argument("--max-iterations", type=int, default=20)
    parser.add_argument("--cerebrum-interval", type=float, default=5.0, help="Min seconds between Cerebrum calls")
    parser.add_argument("--countdown", type=int, default=8, help="Seconds before starting")
    parser.add_argument("--dry-run", action="store_true", help="Use mock components (no game needed)")
    parser.add_argument("--api-key", default=None, help="Zhipu API key (or set ZHIPU_API_KEY)")
    args = parser.parse_args()

    # --- Import factory ---
    from agent_kernel.live_factory import create_live_genshin_loop

    # --- Create loop ---
    log.info("Creating AgentLoop (dry_run=%s)...", args.dry_run)
    agent_loop, capturer, backend = create_live_genshin_loop(
        goal=args.goal,
        window_title=args.window_title,
        api_key=args.api_key,
        max_plan_iterations=args.max_iterations,
        cerebrum_interval_sec=args.cerebrum_interval,
        dry_run=args.dry_run,
    )

    # --- Start capture ---
    capturer.start()
    log.info("Screen capture started")

    # --- Safety countdown ---
    if not args.dry_run and args.countdown > 0:
        log.info("=== SAFETY COUNTDOWN: %d seconds ===", args.countdown)
        log.info("Press Ctrl+C to abort")
        for i in range(args.countdown, 0, -1):
            sys.stdout.write(f"\r  Starting in {i}... ")
            sys.stdout.flush()
            time.sleep(1.0)
        sys.stdout.write("\r  GO!                    \n")

    # --- Build goal and spec ---
    from agent_kernel.types import AgentGoal, TaskSpec
    goal = AgentGoal(
        goal_id=f"goal_{int(time.time())}",
        description=args.goal,
        success_criteria=args.goal,
    )
    spec = TaskSpec(
        task_id=f"task_{int(time.time())}",
        objective=args.goal,
        execution_mode="dry_run" if args.dry_run else "authorized_safe_window",
    )

    # --- Run ---
    log.info("=== AgentLoop starting: goal='%s' ===", args.goal)
    try:
        result = agent_loop.run(goal, spec)
    except KeyboardInterrupt:
        log.warning("=== Interrupted by user (Ctrl+C) ===")
        result = None
    finally:
        capturer.stop()
        try:
            backend.release_all(reason="agent_finished")
        except Exception:
            pass
        log.info("Capture stopped, inputs released")

    # --- Report ---
    if result is not None:
        log.info("=== RESULT ===")
        log.info("  Goal: %s", result.goal_id)
        log.info("  Achieved: %s", result.achieved)
        log.info("  Steps: %d/%d succeeded", result.steps_succeeded, result.steps_total)
        log.info("  Duration: %.1fs", result.total_duration_sec)
        log.info("  Claims: %d verified", len(result.verified_claims))
        if result.error:
            log.info("  Error: %s", result.error)
    else:
        log.info("=== No result (interrupted) ===")


if __name__ == "__main__":
    main()

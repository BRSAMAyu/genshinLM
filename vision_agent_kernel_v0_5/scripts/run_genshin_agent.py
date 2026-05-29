"""Run the Genshin autonomous game agent.

Usage:
    python scripts/run_genshin_agent.py --goal "完成主线任务第一章" --window-title "原神"
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/genshin_agent.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("run_genshin_agent")


def main() -> int:
    parser = argparse.ArgumentParser(description="Genshin autonomous game agent")
    parser.add_argument("--goal", required=True, help="Goal for the agent (e.g. '完成主线任务第一章')")
    parser.add_argument("--window-title", required=True, help="Genshin window title")
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--action-interval", type=float, default=1.5, help="Seconds between actions")
    parser.add_argument("--state-interval", type=float, default=3.0, help="Seconds between VLM analyses")
    parser.add_argument("--plan-interval", type=float, default=15.0, help="Seconds between replans")
    parser.add_argument("--countdown", type=int, default=8, help="Seconds before starting")
    args = parser.parse_args()

    os.makedirs("logs", exist_ok=True)
    os.environ["AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW"] = "1"

    log.info("=" * 60)
    log.info("  Aurora Genshin Agent — Autonomous Mode")
    log.info("=" * 60)
    log.info("  Goal: %s", args.goal)
    log.info("  Window: %s", args.window_title)
    log.info("  Iterations: %d", args.max_iterations)
    log.info("=" * 60)

    # Countdown
    log.info(">>> SWITCH TO GENSHIN NOW — starting in %d seconds <<<", args.countdown)
    for i in range(args.countdown, 0, -1):
        log.info("  %d...", i)
        time.sleep(1.0)
    log.info("  GO!")

    from agent.genshin_game_agent import create_genshin_agent

    brain, perception, backend = create_genshin_agent(
        goal=args.goal,
        window_title=args.window_title,
        max_iterations=args.max_iterations,
        action_interval_sec=args.action_interval,
        state_sample_interval_sec=args.state_interval,
        plan_interval_sec=args.plan_interval,
    )

    perception.start()
    try:
        result = brain.run(goal=args.goal)

        log.info("=" * 60)
        log.info("  RESULT: success=%s iterations=%d actions=%d",
                 result.success, result.iterations, result.actions_taken)
        if result.error:
            log.info("  Error: %s", result.error)
        log.info("  Mission progress: %d/%d", *result.mission_progress)
        log.info("  Duration: %.1f seconds", result.duration_sec)
        log.info("=" * 60)

        return 0 if result.success else 1
    finally:
        perception.stop()
        backend.release_all(reason="agent_finished")


if __name__ == "__main__":
    raise SystemExit(main())

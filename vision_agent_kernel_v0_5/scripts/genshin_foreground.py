"""Foreground agent with log file output.

Runs the ZeroShotAgent with the game in foreground (proven to work).
Logs are written to a file so you can monitor from another terminal:

    Get-Content -Path logs/live_agent.log -Wait
"""
from __future__ import annotations

import io
import os
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.local_secret_store import get_secret


class TeeOutput:
    """Write to both console and log file."""
    def __init__(self, log_path: str) -> None:
        self._log = open(log_path, "w", encoding="utf-8", buffering=1)
        self._stdout = sys.stdout
        self._stderr = sys.stderr

    def write(self, data: str) -> int:
        self._stdout.write(data)
        self._log.write(data)
        return len(data)

    def flush(self) -> None:
        self._stdout.flush()
        self._log.flush()

    def close(self) -> None:
        self._log.close()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Foreground agent with log output")
    parser.add_argument("--game", choices=["genshin", "hsr"], default="genshin")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--window-title", required=True)
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--vlm-interval", type=float, default=2.5)
    parser.add_argument("--countdown", type=int, default=8, help="Seconds before starting")
    args = parser.parse_args()

    os.environ["AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW"] = "1"

    # Set up logging
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "live_agent.log")
    tee = TeeOutput(log_path)
    sys.stdout = tee
    sys.stderr = tee

    api_key = os.getenv("ZHIPU_API_KEY", "") or get_secret("ZHIPU_API_KEY")
    if not api_key:
        print("ERROR: ZHIPU_API_KEY not set")
        return 2

    from agent.zero_shot_agent import ZeroShotAgent

    print("=" * 60)
    print("  Aurora Live Agent — Foreground Mode")
    print("=" * 60)
    print(f"  Game: {args.game}")
    print(f"  Goal: {args.goal}")
    print(f"  Window: {args.window_title}")
    print(f"  Iterations: {args.max_iterations}")
    print(f"  Log: {os.path.abspath(log_path)}")
    print()

    # Countdown
    print(f">>> SWITCH TO THE GAME NOW — starting in {args.countdown} seconds <<<")
    for i in range(args.countdown, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1.0)
    print("  GO!", flush=True)

    agent = ZeroShotAgent(
        game=args.game,
        goal=args.goal,
        api_key=api_key,
        window_title=args.window_title,
        max_iterations=args.max_iterations,
        vlm_interval_sec=args.vlm_interval,
        dry_run=False,
    )

    result = agent.run()

    print("\n" + "=" * 60)
    print(f"  RESULT: ok={result.ok} iterations={result.iterations} actions={result.actions_taken}")
    if result.error:
        print(f"  Error: {result.error}")
    print("=" * 60)

    tee.close()
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

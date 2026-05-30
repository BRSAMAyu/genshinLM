"""Zero-shot QA/testbed control agent: capture -> VLM -> LLM -> safe backend.

Usage:
    # Store your local API key once:
    python scripts/manage_local_secrets.py set ZHIPU_API_KEY

    # Run against an Aurora safe-window/testbed title:
    python scripts/run_zero_shot.py --game genshin --goal "walk to the waypoint" --window "Aurora Genshin-like Testbed"

    # Use Coding Plan endpoint:
    python scripts/run_zero_shot.py --game genshin --goal "walk forward" --base-url https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from agent.zero_shot_agent import ZeroShotAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Zero-shot QA/testbed control agent")
    parser.add_argument("--game", choices=["genshin", "hsr"], default="genshin", help="Target game")
    parser.add_argument("--goal", type=str, required=True, help="What you want the agent to achieve")
    parser.add_argument("--api-key", type=str, default=None, help="Zhipu API key (or set ZHIPU_API_KEY)")
    parser.add_argument("--base-url", type=str, default=None, help="API base URL override")
    parser.add_argument("--vlm-model", type=str, default="glm-4v-flash", help="VLM model name")
    parser.add_argument("--llm-model", type=str, default="glm-5.1", help="LLM model name")
    parser.add_argument("--window", type=str, default=None, help="Game window title override")
    parser.add_argument("--max-iterations", type=int, default=30, help="Max agent loop iterations")
    parser.add_argument("--vlm-interval", type=float, default=3.0, help="Seconds between VLM calls")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send input only to an explicitly authorized Aurora QA safe-window",
    )
    args = parser.parse_args()

    from core.local_secret_store import get_secret

    api_key = args.api_key or os.getenv("ZHIPU_API_KEY", "") or get_secret("ZHIPU_API_KEY")
    if not api_key:
        print("Error: ZHIPU_API_KEY not set. Use --api-key, set env var, or run:")
        print("  python scripts/manage_local_secrets.py set ZHIPU_API_KEY")
        sys.exit(1)

    base_url = args.base_url or os.getenv(
        "ZHIPU_BASE_URL",
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    )

    print("=" * 60, flush=True)
    print("Zero-Shot QA/Testbed Control Agent", flush=True)
    print(f"  Game: {args.game}", flush=True)
    print(f"  Goal: {args.goal}", flush=True)
    print(f"  VLM:  {args.vlm_model}", flush=True)
    print(f"  LLM:  {args.llm_model}", flush=True)
    print(f"  Max iterations: {args.max_iterations}", flush=True)
    print("=" * 60, flush=True)

    agent = ZeroShotAgent(
        game=args.game,
        goal=args.goal,
        api_key=api_key,
        vlm_model=args.vlm_model,
        llm_model=args.llm_model,
        base_url=base_url,
        window_title=args.window,
        max_iterations=args.max_iterations,
        vlm_interval_sec=args.vlm_interval,
        dry_run=(not args.execute) or args.dry_run,
    )

    result = agent.run()

    print("\n" + "=" * 60, flush=True)
    print("RESULT", flush=True)
    print(f"  Success: {result.ok}", flush=True)
    print(f"  Iterations: {result.iterations}", flush=True)
    print(f"  Actions taken: {result.actions_taken}", flush=True)
    print(f"  Final scene: {result.final_analysis}", flush=True)
    if result.error:
        print(f"  Error: {result.error}", flush=True)
    print("=" * 60, flush=True)

    report_path = f"logs/zero_shot_{args.game}_{int(__import__('time').time())}.json"
    try:
        import pathlib
        pathlib.Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(report_path).write_text(
            json.dumps({
                "ok": result.ok,
                "goal": result.goal,
                "iterations": result.iterations,
                "actions_taken": result.actions_taken,
                "history": result.history,
                "final_analysis": result.final_analysis,
                "error": result.error,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Report saved to: {report_path}", flush=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()

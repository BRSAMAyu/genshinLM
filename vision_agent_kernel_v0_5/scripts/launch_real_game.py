"""Authorized live-window QA launcher.

This keeps real-machine integration possible without hardcoding a commercial
client, scanning processes, injecting API keys, or bypassing SafeWindowInput.
The operator must provide the target window title and opt in explicitly before
non-dry-run input is enabled.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurora authorized live-window QA launcher")
    parser.add_argument("--game", choices=["genshin", "hsr"], default="genshin")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--window-title", required=True)
    parser.add_argument("--alt-window-title", action="append", default=[])
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--vlm-model", default="glm-4v-flash")
    parser.add_argument("--llm-model", default="glm-5.1")
    parser.add_argument("--max-iterations", type=int, default=30)
    parser.add_argument("--vlm-interval", type=float, default=3.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backend", choices=["safe_window", "background", "flash_focus"],
                        default="safe_window",
                        help="Input backend mode. 'background'=PostMessage(no focus needed), "
                             "'flash_focus'=brief foreground flash. Default: safe_window")
    parser.add_argument(
        "--i-understand-authorized-window",
        action="store_true",
        help="Required with --execute; confirms the target is an authorized QA window.",
    )
    args = parser.parse_args()

    dry_run = not args.execute
    if args.execute and not args.i_understand_authorized_window:
        print("--execute requires --i-understand-authorized-window")
        return 2

    from core.local_secret_store import get_secret

    api_key = args.api_key or os.getenv("ZHIPU_API_KEY", "") or get_secret("ZHIPU_API_KEY")
    if not api_key:
        print("ZHIPU_API_KEY is not set. Pass --api-key, set the env var, or run:")
        print("  python scripts/manage_local_secrets.py set ZHIPU_API_KEY")
        return 2

    if args.execute:
        os.environ["AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW"] = "1"

    from agent.zero_shot_agent import ZeroShotAgent

    agent = ZeroShotAgent(
        game=args.game,
        goal=args.goal,
        api_key=api_key,
        vlm_model=args.vlm_model,
        llm_model=args.llm_model,
        base_url=args.base_url or os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
        window_title=args.window_title,
        alt_window_titles=list(args.alt_window_title),
        max_iterations=args.max_iterations,
        vlm_interval_sec=args.vlm_interval,
        dry_run=dry_run,
        backend_mode=args.backend,
    )
    result = agent.run()
    print(f"ok={result.ok} iterations={result.iterations} actions={result.actions_taken} error={result.error}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

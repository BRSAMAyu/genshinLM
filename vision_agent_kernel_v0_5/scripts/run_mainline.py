"""Autonomous mainline progression entry point.

Usage:
    python scripts/run_mainline.py --dry-run
    python scripts/run_mainline.py --window-title "原神"
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mainline")


def _build_components(dry_run: bool = True, window_title: str = ""):
    from execution.console_backend import ConsoleInputBackend
    from execution.safe_window_backend import SafeWindowInputBackend
    from perception.genshin_screen_classifier import GenshinScreenClassifier
    from planning.screen_state_claim_builder import ScreenStateClaimBuilder
    from planning.quest_state_machine import QuestStateMachine
    from knowledge.genshin_archon_quests import ARCHON_QUESTS

    classifier = GenshinScreenClassifier()
    claim_builder = ScreenStateClaimBuilder()

    if dry_run:
        backend = ConsoleInputBackend()
    else:
        backend = SafeWindowInputBackend(target_window_title=window_title)

    quest_sm = QuestStateMachine(ARCHON_QUESTS)

    return {
        "classifier": classifier,
        "claim_builder": claim_builder,
        "backend": backend,
        "quest_sm": quest_sm,
    }


def _load_progress(path: str, quest_sm) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        quest_sm.load_state(state)
        log.info("Loaded progress: quest %d, step %d", quest_sm._current_quest_idx, quest_sm._current_step_idx)
    except Exception as exc:
        log.warning("Failed to load progress: %s", exc)


def _save_progress(path: str, quest_sm) -> None:
    try:
        state = quest_sm.save_state()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        log.info("Progress saved to %s", path)
    except Exception as exc:
        log.warning("Failed to save progress: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aurora Mainline Progression")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Use console backend (default)")
    parser.add_argument("--window-title", type=str, default="", help="Target window title for real input")
    parser.add_argument(
        "--enable-bagel-experimental",
        action="store_true",
        default=False,
        help="Enable BAGEL experimental attribution path (disabled by default).",
    )
    parser.add_argument("--save-path", type=str, default="mainline_progress.json", help="Progress save file")
    args = parser.parse_args()

    dry_run = args.dry_run or not args.window_title
    log.info("Starting mainline progression (dry_run=%s)", dry_run)

    components = _build_components(dry_run=dry_run, window_title=args.window_title)
    quest_sm = components["quest_sm"]

    _load_progress(args.save_path, quest_sm)

    shutdown = threading.Event()

    def _on_signal(*_args):
        log.info("Shutdown requested")
        shutdown.set()

    import signal
    signal.signal(signal.SIGINT, _on_signal)

    step = quest_sm.current_step
    log.info("Current step: %s", step)

    try:
        while not shutdown.is_set() and step is not None:
            log.info(
                "Executing: [%s] %s — %s",
                step.step_id, step.description, step.objective,
            )
            if dry_run:
                log.info("  (dry-run) auto-completing step")
                step = quest_sm.advance(evidence="dry_run")
                continue

            log.info("Starting live execution via MainlineLiveBridge")
            from planning.mainline.mainline_live_bridge import MainlineLiveBridge
            from planning.mainline.mission_graph_v4 import MissionGraphV4, MissionNodeV4, ClaimContract

            graph = MissionGraphV4(mission_id=step.step_id)
            node = MissionNodeV4(
                node_id=step.step_id,
                node_type="navigate_walk" if "walk" in step.objective.lower() else "interact",
                skill_candidates=("quest_follow",) if "walk" in step.objective.lower() else ("interact",),
                output_claims=(
                    ClaimContract(
                        claim_type="objective_complete",
                        target=step.objective,
                        required_status="verified",
                        claim_role="terminal",
                    ),
                ),
            )
            graph.add_node(node)

            bridge = MainlineLiveBridge(
                window_title=args.window_title,
                enable_bagel_experimental=args.enable_bagel_experimental,
            )
            try:
                res = bridge.execute_live_mission(graph)
                if res.success:
                    step = quest_sm.advance(evidence="live_success")
                else:
                    log.error("Live execution failed for step %s", step.step_id)
                    break
            finally:
                bridge.stop()
    finally:
        _save_progress(args.save_path, quest_sm)
        if quest_sm.is_mainline_complete():
            log.info("All mainline quests completed!")
        else:
            log.info("Stopped at quest %d, step %d", quest_sm._current_quest_idx, quest_sm._current_step_idx)


if __name__ == "__main__":
    main()

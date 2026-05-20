from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DIRECTORIES: tuple[str, ...] = (
    "configs",
    "core",
    "perception",
    "control",
    "execution",
    "orchestration",
    "telemetry",
    "testbed",
    "scripts",
    "action_blocks",
    "tests",
)

FILES: tuple[str, ...] = (
    "README.md",
    "ARCHITECTURE.md",
    "SAFETY.md",
    "pyproject.toml",
    "requirements.txt",
    "configs/default.yaml",
    "configs/perception.yaml",
    "configs/control.yaml",
    "configs/input.yaml",
    "configs/telemetry.yaml",
    "configs/model.yaml",
    "configs/testbed.yaml",
    "core/__init__.py",
    "core/timebase.py",
    "core/enums.py",
    "core/types.py",
    "core/events.py",
    "core/state_bus.py",
    "core/mode_arbiter.py",
    "core/runtime_health.py",
    "core/watchdog.py",
    "perception/__init__.py",
    "perception/capture_base.py",
    "perception/dxcam_capture.py",
    "perception/mss_capture.py",
    "perception/viewport.py",
    "perception/detector_base.py",
    "perception/yolo_detector.py",
    "perception/tracker_base.py",
    "perception/ultralytics_tracker.py",
    "perception/target_selector.py",
    "perception/depth_base.py",
    "perception/depth_anything_estimator.py",
    "perception/ui_detector.py",
    "perception/visual_trigger_detector.py",
    "perception/pipeline.py",
    "control/__init__.py",
    "control/camera_model.py",
    "control/camera_servo.py",
    "control/movement_controller.py",
    "control/progress_supervisor.py",
    "control/recovery_policy.py",
    "control/obstacle_policy.py",
    "control/controller_loop.py",
    "execution/__init__.py",
    "execution/input_backend_base.py",
    "execution/console_backend.py",
    "execution/safe_window_backend.py",
    "execution/real_input_backend.py",
    "execution/input_lease.py",
    "execution/input_worker.py",
    "execution/action_block.py",
    "execution/visual_action_block.py",
    "execution/human_override.py",
    "orchestration/__init__.py",
    "orchestration/graph.py",
    "orchestration/skill_base.py",
    "orchestration/skills.py",
    "orchestration/orchestrator.py",
    "orchestration/interrupt_handler.py",
    "orchestration/failure_policy.py",
    "telemetry/__init__.py",
    "telemetry/logger.py",
    "telemetry/event_schema.py",
    "telemetry/video_recorder.py",
    "telemetry/replay_index.py",
    "telemetry/metrics.py",
    "testbed/__init__.py",
    "testbed/pseudo3d_scene.py",
    "testbed/moving_target_env.py",
    "testbed/unity_bridge_stub.py",
    "scripts/run_kernel.py",
    "scripts/run_testbed.py",
    "scripts/calibrate_viewport.py",
    "scripts/calibrate_camera.py",
    "scripts/test_capture.py",
    "scripts/replay_run.py",
    "action_blocks/demo_visual_action_block.yaml",
    "tests/test_state_bus.py",
    "tests/test_interrupt_priority.py",
    "tests/test_input_lease.py",
    "tests/test_deadman_switch.py",
    "tests/test_mode_arbiter.py",
    "tests/test_progress_supervisor.py",
)


def create_project_tree(root: Path = ROOT) -> None:
    for directory in DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)

    for file_name in FILES:
        file_path = root / file_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch(exist_ok=True)


if __name__ == "__main__":
    create_project_tree()
    print(f"Created project tree under {ROOT}")

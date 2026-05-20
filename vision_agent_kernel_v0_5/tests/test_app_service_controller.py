from __future__ import annotations

from app_service.agent_controller import AgentController


def test_agent_controller_defaults_to_stopped_dry_run() -> None:
    controller = AgentController()

    state = controller.state()

    assert state.mode == "STOPPED"
    assert state.input_backend == "console"
    assert state.focus_status == "DRY_RUN"
    assert state.input_released is True


def test_agent_controller_start_pause_resume_stop() -> None:
    controller = AgentController()

    running = controller.start()
    paused = controller.pause()
    resumed = controller.resume()
    stopped = controller.stop()

    assert running.mode == "RUNNING"
    assert paused.mode == "PAUSED"
    assert resumed.mode == "RUNNING"
    assert stopped.mode == "STOPPED"
    assert stopped.runtime_health.release_all_called is True


def test_agent_controller_emergency_stop_releases_input() -> None:
    controller = AgentController()
    controller.start()

    stopped = controller.emergency_stop()

    assert stopped.mode == "EMERGENCY_STOPPED"
    assert stopped.active_interrupt is not None
    assert stopped.active_interrupt["code"] == "EMERGENCY_STOP"
    assert stopped.runtime_health.release_all_called is True

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from planning.mainline.mainline_live_bridge import MainlineLiveBridge
from planning.mainline.mission_graph_v4 import MissionGraphV4


@patch("planning.mainline.mainline_live_bridge.SafeWindowInputBackend")
@patch("planning.mainline.mainline_live_bridge.InputWorker")
def test_mainline_live_bridge_initialization(
    mock_input_worker: MagicMock,
    mock_backend: MagicMock,
) -> None:
    # Setup mock behaviors
    mock_worker_inst = MagicMock()
    mock_worker_inst.is_alive = False
    mock_input_worker.return_value = mock_worker_inst

    mock_backend_inst = MagicMock()
    mock_backend.return_value = mock_backend_inst

    bridge = MainlineLiveBridge(window_title="TestWindow")

    assert bridge._window_title == "TestWindow"
    assert bridge._backend is mock_backend_inst
    assert bridge._worker is mock_worker_inst

    # Should have started the worker
    mock_worker_inst.start.assert_called_once()


@patch("planning.mainline.mainline_live_bridge.SafeWindowInputBackend")
@patch("planning.mainline.mainline_live_bridge.InputWorker")
def test_mainline_live_bridge_execute_live_mission(
    mock_input_worker: MagicMock,
    mock_backend: MagicMock,
) -> None:
    mock_worker_inst = MagicMock()
    mock_worker_inst.is_alive = True
    mock_input_worker.return_value = mock_worker_inst

    mock_backend_inst = MagicMock()
    mock_backend_inst.is_target_focused.return_value = True
    mock_backend.return_value = mock_backend_inst

    bridge = MainlineLiveBridge(window_title="TestWindow")

    # Mock the runner
    mock_runner = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.duration_sec = 5.0
    mock_runner.run.return_value = mock_result
    bridge._runner = mock_runner

    graph = MissionGraphV4(mission_id="m_live")

    res = bridge.execute_live_mission(graph)

    # Should have focused the window
    mock_backend_inst.focus_target_window.assert_called_once()
    # Should have run the runner
    mock_runner.run.assert_called_once_with(graph)

    assert res.success is True
    assert res.duration_sec == 5.0

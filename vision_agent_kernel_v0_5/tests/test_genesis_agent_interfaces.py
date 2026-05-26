from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

from app_service.launcher import DiagnosticReport, GenesisLauncher
from core.state_bus import StateBus
from core.types import FocusState, Observation
from planning.strategy_reader import StrategyReader, WebSearchClient
from reflex.combat_director import CombatDirector


class _Lease:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, float | None]] = []

    def press(self, value: str, duration: float = 0.0) -> None:
        self.events.append(("press", value, duration))

    def click(self, value: str, duration: float = 0.0) -> None:
        self.events.append(("click", value, duration))

    def release_all(self) -> None:
        self.events.append(("release_all", None, None))


def _observation(**extensions: object) -> Observation:
    return Observation(
        frame_id=1,
        t_capture=0.0,
        t_processed=0.0,
        latency_ms=0.0,
        viewport_size=(1280, 720),
        target_track=None,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={},
        os_focus=FocusState(True, "sandbox", "sandbox"),
        extensions=dict(extensions),
    )


def test_launcher_diagnostics_does_not_auto_repair(monkeypatch):
    launcher = GenesisLauncher()
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("diagnostics must not install dependencies")

    monkeypatch.setattr(subprocess, "run", fail_if_called)
    report = launcher.run_diagnostics()
    assert isinstance(report.errors, list)
    assert not called


def test_launcher_frontend_uses_argument_list_not_shell(monkeypatch):
    launcher = GenesisLauncher()
    popen_calls: list[dict[str, object]] = []

    monkeypatch.setattr("app_service.launcher.shutil.which", lambda name: "npm.cmd" if name == "npm" else None)

    class _Proc:
        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        popen_calls.append({"cmd": cmd, **kwargs})
        return _Proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    assert launcher.start_frontend("dev")
    assert popen_calls[0]["cmd"] == ["npm.cmd", "run", "dev"]
    assert popen_calls[0].get("shell") is None


def test_launcher_repair_uses_argument_lists_not_shell(monkeypatch):
    launcher = GenesisLauncher()
    run_calls: list[dict[str, object]] = []

    monkeypatch.setattr("app_service.launcher.shutil.which", lambda name: "npm.cmd" if name == "npm" else None)
    monkeypatch.setattr("app_service.launcher.Path.exists", lambda self: False if str(self).endswith("node_modules") else True)

    def fake_run(cmd, **kwargs):
        run_calls.append({"cmd": cmd, **kwargs})
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    report = DiagnosticReport(
        python_ok=True,
        node_ok=True,
        requirements_ok=True,
        gui_built=False,
        port_available=True,
    )
    assert launcher.auto_repair(report)
    assert run_calls[0]["cmd"] == ["npm.cmd", "install"]
    assert run_calls[0].get("shell") is None
    assert run_calls[1]["cmd"] == ["npm.cmd", "run", "build"]
    assert run_calls[1].get("shell") is None


def test_combat_director_executes_combo_without_blocking_sleep(monkeypatch):
    monkeypatch.setattr("reflex.combat_director.time.sleep", lambda *_: (_ for _ in ()).throw(AssertionError("blocking sleep used")))
    bus = StateBus()
    lease = _Lease()
    director = CombatDirector(bus, lease, {
        "combos": {
            "basic": {
                "cooldown": 0.0,
                "steps": [
                    {"action_type": "key_press", "value": "e", "duration": 0.01, "post_delay": 0.0},
                    {"action_type": "mouse_click", "value": "left", "duration": 0.01, "post_delay": 0.0},
                ],
            }
        }
    })

    assert director.trigger_combo("basic")
    director.update(_observation())
    director.update(_observation())
    assert lease.events == [("press", "e", 0.01), ("click", "left", 0.01)]


def test_combat_director_preemption_releases_all():
    bus = StateBus()
    bus.register_slot("reflex.active_preemption_token").put({"reason": "danger"})
    lease = _Lease()
    director = CombatDirector(bus, lease, {
        "combos": {
            "basic": {
                "cooldown": 0.0,
                "steps": [{"action_type": "key_press", "value": "e"}],
            }
        }
    })

    assert director.trigger_combo("basic")
    director.update(_observation())
    assert lease.events == [("release_all", None, None)]


def test_strategy_reader_compiles_deterministic_macro_graph():
    search = MagicMock(spec=WebSearchClient)
    search.search.return_value = (
        "To beat Dvalin: Attack his claws, then climb and attack the clot, then escape burning platforms."
    )
    graph = StrategyReader(search).retrieve_strategy_for_goal("Stormterror Dvalin", game_id="genshin")
    assert search.search.called
    assert graph.goal == "Stormterror Dvalin"
    assert [node.expected_state for node in graph.nodes] == [
        "shield_broken",
        "boss_hp_reduced",
        "platform_changed",
    ]
    assert graph.edges == [("storm_1", "storm_2"), ("storm_2", "storm_3")]

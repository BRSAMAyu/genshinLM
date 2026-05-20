from __future__ import annotations

from dataclasses import dataclass

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from execution.input_worker import InputWorker


@dataclass(frozen=True, slots=True)
class HumanOverrideConfig:
    emergency_hotkey: str = "F9"
    pause_hotkey: str = "F8"


class HumanOverride:
    def __init__(
        self,
        input_worker: InputWorker,
        state_bus: StateBus | None = None,
        timebase: Timebase | None = None,
        config: HumanOverrideConfig | None = None,
    ) -> None:
        self._input_worker = input_worker
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()
        self._config = config or HumanOverrideConfig()

    def trigger_emergency_stop(self, reason: str = "human_override") -> Interrupt:
        interrupt = Interrupt(
            priority=0,
            timestamp=self._timebase.now(),
            code="EMERGENCY_STOP",
            source="human_override",
            payload={"reason": reason, "hotkey": self._config.emergency_hotkey},
            recoverable=False,
            requires_input_release=True,
        )
        print(
            "[HumanOverride] "
            f"{interrupt.timestamp:.6f} emergency stop requested reason={reason!r}",
            flush=True,
        )
        self._input_worker.submit_interrupt(interrupt)
        if self._state_bus is not None:
            self._state_bus.publish_interrupt(interrupt)
        return interrupt

    def request_pause(self, reason: str = "human_pause") -> Interrupt:
        interrupt = Interrupt(
            priority=1,
            timestamp=self._timebase.now(),
            code="HUMAN_PAUSE",
            source="human_override",
            payload={"reason": reason, "hotkey": self._config.pause_hotkey},
            recoverable=True,
            requires_input_release=True,
        )
        print(
            "[HumanOverride] "
            f"{interrupt.timestamp:.6f} pause requested reason={reason!r}",
            flush=True,
        )
        self._input_worker.submit_interrupt(interrupt)
        if self._state_bus is not None:
            self._state_bus.publish_interrupt(interrupt)
        return interrupt

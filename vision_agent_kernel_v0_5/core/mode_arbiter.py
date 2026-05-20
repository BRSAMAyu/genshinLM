from __future__ import annotations

import threading
from dataclasses import dataclass

from core.events import ModeRequest
from core.state_bus import StateBus


IDLE = "IDLE"
CALIBRATING = "CALIBRATING"
RUNNING_ACTION_BLOCK = "RUNNING_ACTION_BLOCK"
ACQUIRING_TARGET = "ACQUIRING_TARGET"
TRACKING_TARGET = "TRACKING_TARGET"
APPROACHING_TARGET = "APPROACHING_TARGET"
EXECUTING_VISUAL_ACTION = "EXECUTING_VISUAL_ACTION"
RECOVERING = "RECOVERING"
PAUSED = "PAUSED"
COMPLETE = "COMPLETE"
FAILED = "FAILED"
EMERGENCY_STOPPED = "EMERGENCY_STOPPED"

VALID_MODES: frozenset[str] = frozenset(
    {
        IDLE,
        CALIBRATING,
        RUNNING_ACTION_BLOCK,
        ACQUIRING_TARGET,
        TRACKING_TARGET,
        APPROACHING_TARGET,
        EXECUTING_VISUAL_ACTION,
        RECOVERING,
        PAUSED,
        COMPLETE,
        FAILED,
        EMERGENCY_STOPPED,
    }
)

P0_EMERGENCY = 0
P1_WATCHDOG = 10
P2_HUMAN_OVERRIDE = 20
P3_ACTION_BLOCK_EXCLUSIVE = 30
P4_RECOVERY = 40
P5_TRACKING = 50
P6_IDLE = 100

TERMINAL_MODES: frozenset[str] = frozenset({COMPLETE, FAILED, EMERGENCY_STOPPED})


@dataclass(frozen=True, slots=True)
class ModeDecision:
    accepted: bool
    current_mode: str
    request: ModeRequest
    reason: str


class ModeArbiter:
    def __init__(self, initial_mode: str = IDLE) -> None:
        if initial_mode not in VALID_MODES:
            raise ValueError(f"invalid initial mode: {initial_mode}")
        self._lock = threading.RLock()
        self._current_mode = initial_mode
        self._active_request: ModeRequest | None = None

    @property
    def current_mode(self) -> str:
        with self._lock:
            return self._current_mode

    def submit(self, request: ModeRequest) -> ModeDecision:
        if request.requested_mode not in VALID_MODES:
            raise ValueError(f"invalid requested mode: {request.requested_mode}")

        with self._lock:
            if not self._can_preempt_locked(request):
                return ModeDecision(
                    accepted=False,
                    current_mode=self._current_mode,
                    request=request,
                    reason="lower_priority_request_rejected",
                )

            self._current_mode = request.requested_mode
            self._active_request = request
            return ModeDecision(
                accepted=True,
                current_mode=self._current_mode,
                request=request,
                reason="accepted",
            )

    def drain_once(self, state_bus: StateBus) -> ModeDecision | None:
        request = state_bus.next_mode_request(timeout=0.0)
        if request is None:
            return None
        decision = self.submit(request)
        if decision.accepted:
            state_bus.current_mode.put(decision.current_mode)
        return decision

    def _can_preempt_locked(self, request: ModeRequest) -> bool:
        if self._active_request is None:
            return True
        if self._current_mode == EMERGENCY_STOPPED:
            return request.requested_mode == EMERGENCY_STOPPED
        if self._current_mode in TERMINAL_MODES and request.priority > P0_EMERGENCY:
            return False
        if request.priority < self._active_request.priority:
            return True
        if request.priority == self._active_request.priority:
            return request.timestamp >= self._active_request.timestamp
        return False

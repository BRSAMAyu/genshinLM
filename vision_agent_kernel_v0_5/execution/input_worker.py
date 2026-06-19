from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any
from typing import Literal

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease
from execution.console_backend import ConsoleInputBackend
from execution.input_lease import DOWN, UP, InputLeaseStore


CommandKind = Literal["lease", "interrupt", "stop"]


@dataclass(frozen=True, slots=True)
class InputWorkerCommand:
    kind: CommandKind
    payload: InputLease | Interrupt | None = None


class InputWorker:
    def __init__(
        self,
        backend: ConsoleInputBackend | None = None,
        timebase: Timebase | None = None,
        tick_seconds: float = 0.01,
        command_queue_size: int = 1024,
        release_on_stop: bool = True,
        state_bus: StateBus | None = None,
        target_window_title: str | None = None,
    ) -> None:
        self._timebase = timebase or Timebase()
        self._backend = backend or ConsoleInputBackend(self._timebase)
        self._lease_store = InputLeaseStore()
        self._tick_seconds = tick_seconds
        self._release_on_stop = release_on_stop
        self._commands: queue.Queue[InputWorkerCommand] = queue.Queue(maxsize=command_queue_size)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._started = threading.Event()
        self._focus_lost_published = False
        self._focus_lock = threading.Lock()
        self._log_lock = threading.RLock()
        self._state_bus = state_bus
        self._target_window_title = target_window_title
        self._lease_lock = threading.RLock()

    @property
    def lease_lock(self) -> threading.RLock:
        return self._lease_lock

    @property
    def backend(self) -> ConsoleInputBackend:
        return self._backend

    @property
    def lease_store(self) -> InputLeaseStore:
        return self._lease_store

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._log("start ignored; worker already running")
            return
        self._log("starting background input event loop")
        self._stop_event.clear()
        self._started.clear()
        self._thread = threading.Thread(target=self._run_loop, name="input-worker", daemon=True)
        self._thread.start()
        self._started.wait(timeout=1.0)

    def submit_lease(self, lease: InputLease) -> bool:
        return self._submit(InputWorkerCommand(kind="lease", payload=lease))

    def submit_interrupt(self, interrupt: Interrupt) -> bool:
        return self._submit(InputWorkerCommand(kind="interrupt", payload=interrupt))

    def stop(self, timeout: float | None = 2.0) -> None:
        self._log("stop requested")
        self._stop_event.set()
        self._submit(InputWorkerCommand(kind="stop"))
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        if self._thread is not None and self._thread.is_alive():
            self._log("worker did not stop within timeout")

    def active_keys_snapshot(self) -> set[str]:
        return self._lease_store.active_key_snapshot()

    def _submit(self, command: InputWorkerCommand) -> bool:
        try:
            self._commands.put_nowait(command)
        except queue.Full:
            if command.kind in {"interrupt", "stop"}:
                # Critical commands must not be dropped. Try to evict one lease.
                if self._evict_one_lease_command():
                    try:
                        self._commands.put_nowait(command)
                        self._log(f"queue full; evicted one lease to enqueue critical {command.kind}")
                        return True
                    except queue.Full:
                        pass
                try:
                    self._commands.put(command, timeout=self._tick_seconds)
                    self._log(f"queue full; blocked briefly to enqueue critical {command.kind}")
                    return True
                except queue.Full:
                    self._log(f"critical command dropped after retries: {command.kind}")
                    return False
            self._log(f"command queue full; dropped {command.kind}")
            return False
        self._log(f"queued command kind={command.kind}")
        return True

    def _evict_one_lease_command(self) -> bool:
        with self._lease_lock:
            evicted_lease_id: str | None = None
            try:
                buffered: list[InputWorkerCommand] = []
                evicted = False
                while True:
                    item = self._commands.get_nowait()
                    if not evicted and item.kind == "lease":
                        evicted = True
                        evicted_lease_id = getattr(item.payload, "lease_id", None) if hasattr(item, "payload") else None
                        continue
                    buffered.append(item)
            except queue.Empty:
                pass
            for item in buffered:
                try:
                    self._commands.put_nowait(item)
                except queue.Full:
                    break
            # Remove evicted lease from store to prevent stale active state
            if evicted and evicted_lease_id is not None:
                try:
                    self._lease_store.remove(evicted_lease_id)
                except Exception:
                    pass
            return evicted

    def _run_loop(self) -> None:
        self._started.set()
        self._log("background input event loop entered")
        try:
            while not self._stop_event.is_set():
                self._drain_one_command()
                self._run_deadman_check()
                self._run_focus_check()
        except BaseException as exc:
            self._log(f"fatal worker exception: {exc!r}; forcing release_all")
            cleared = self._lease_store.clear()
            for lease in cleared:
                for key, state in lease.key_states.items():
                    if state == DOWN:
                        self._backend.key_up(key, reason="input_worker_exception")
            self._backend.release_all(reason="input_worker_exception")
            raise
        finally:
            if self._release_on_stop:
                self._log("finally release_all on worker exit")
                cleared = self._lease_store.clear()
                for lease in cleared:
                    for key, state in lease.key_states.items():
                        if state == DOWN:
                            self._backend.key_up(key, reason="input_worker_exit")
                self._backend.release_all(reason="input_worker_exit")
            self._log("background input event loop exited")

    def _drain_one_command(self) -> None:
        try:
            command = self._commands.get(timeout=self._tick_seconds)
        except queue.Empty:
            return

        self._log(f"processing command kind={command.kind}")
        if command.kind == "lease" and isinstance(command.payload, InputLease):
            self._apply_lease(command.payload)
        elif command.kind == "interrupt" and isinstance(command.payload, Interrupt):
            self._handle_interrupt(command.payload)
        elif command.kind == "stop":
            self._stop_event.set()
            self._log("stop command accepted")

    def _apply_lease(self, lease: InputLease) -> None:
        now = self._timebase.now()
        validation = self._lease_store.validate(lease, now=now)
        if not validation.valid:
            self._log(f"rejected lease_id={lease.lease_id}: {validation.reason}")
            return

        self._log(
            "applying lease "
            f"lease_id={lease.lease_id} owner={lease.owner} priority={lease.priority} "
            f"expires_at={lease.expires_at:.6f} reason={lease.reason!r}"
        )
        for key, state in lease.key_states.items():
            if state == DOWN:
                self._backend.key_down(key, reason=lease.reason)
            elif state == UP:
                self._backend.key_up(key, reason=lease.reason)

        if lease.mouse_delta is not None:
            dx, dy = lease.mouse_delta
            self._backend.mouse_move(dx, dy, reason=lease.reason)

        # Execute optional atomic actions (click/scroll/type/combo/etc).
        for action in lease.actions:
            self._apply_atomic_action(action, lease.reason)

        if any(state == DOWN for state in lease.key_states.values()):
            self._lease_store.add(lease)
            self._log(f"lease_id={lease.lease_id} registered for deadman supervision")

    def _apply_atomic_action(self, action: dict[str, Any], reason: str) -> None:
        action_type = str(action.get("type", "")).lower()
        if not action_type:
            return
        if action_type == "left_click" and hasattr(self._backend, "left_click"):
            self._backend.left_click(reason=reason)
            return
        if action_type == "right_click" and hasattr(self._backend, "right_click"):
            self._backend.right_click(reason=reason)
            return
        if action_type == "mouse_scroll" and hasattr(self._backend, "mouse_scroll"):
            delta = int(action.get("delta", -1))
            self._backend.mouse_scroll(delta=delta, reason=reason)
            return
        if action_type == "type_text" and hasattr(self._backend, "type_text"):
            text = str(action.get("text", ""))
            delay_ms = int(action.get("delay_between_keys_ms", 50))
            self._backend.type_text(text=text, delay_between_keys_ms=delay_ms, reason=reason)
            return
        if action_type == "execute_combo" and hasattr(self._backend, "execute_combo"):
            keys = [str(k) for k in action.get("keys", [])]
            hold_ms = int(action.get("hold_time_ms", 100))
            self._backend.execute_combo(keys=keys, hold_time_ms=hold_ms, reason=reason)
            return
        self._log(f"unsupported atomic action ignored: {action_type}")

    def _handle_interrupt(self, interrupt: Interrupt) -> None:
        self._log(
            "handling interrupt "
            f"priority={interrupt.priority} code={interrupt.code} source={interrupt.source} "
            f"requires_input_release={interrupt.requires_input_release}"
        )
        if interrupt.priority == 0 or interrupt.requires_input_release:
            cleared = self._lease_store.clear()
            self._log(
                f"interrupt requires release_all; cleared_leases={len(cleared)} "
                f"code={interrupt.code}"
            )
            for lease in cleared:
                for key, state in lease.key_states.items():
                    if state == DOWN:
                        self._backend.key_up(key, reason=f"interrupt:{interrupt.code}")
            self._backend.release_all(reason=f"interrupt:{interrupt.code}")

    def _run_deadman_check(self) -> None:
        now = self._timebase.now()
        expired = self._lease_store.expire_due(now)
        if not expired.expired_lease_ids:
            return

        self._log(
            "deadman expired leases "
            f"now={now:.6f} lease_ids={expired.expired_lease_ids} "
            f"keys_to_release={expired.keys_to_release}"
        )
        for key in expired.keys_to_release:
            self._backend.key_up(key, reason="deadman_expired")

    def _run_focus_check(self) -> None:
        if hasattr(self._backend, "is_target_focused"):
            focused = True
            try:
                focused = self._backend.is_target_focused()
            except Exception as e:
                self._log(f"Error checking window focus: {e}")
                focused = False

            with self._focus_lock:
                if not focused and not self._focus_lost_published:
                    self._log("Target window focus lost! Activating physical deadman safety switch.")
                    cleared = self._lease_store.clear()
                    for lease in cleared:
                        for key, state in lease.key_states.items():
                            if state == DOWN:
                                self._backend.key_up(key, reason="focus_lost")
                    self._backend.release_all(reason="focus_lost")
                    self._focus_lost_published = True
                    if self._state_bus is not None:
                        self._state_bus.publish_interrupt(
                            Interrupt(
                                priority=0,
                                timestamp=self._timebase.now(),
                                code="FOCUS_LOST",
                                source="InputWorker",
                                recoverable=True,
                                requires_input_release=True,
                            )
                        )
                elif focused and self._focus_lost_published:
                    self._focus_lost_published = False
                    self._log("Target window focus recovered. Resuming normal operation.")
                    if self._state_bus is not None:
                        self._state_bus.publish_interrupt(
                            Interrupt(
                                priority=50,
                                timestamp=self._timebase.now(),
                                code="FOCUS_RECOVERED",
                                source="InputWorker",
                                recoverable=True,
                                requires_input_release=False,
                            )
                        )

    def _log(self, message: str) -> None:
        with self._log_lock:
            print(f"[InputWorker] {self._timebase.now():.6f} {message}", flush=True)

    def __enter__(self) -> InputWorker:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()

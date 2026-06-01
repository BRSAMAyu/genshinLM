"""InputLeaseManagerImpl — concrete L0 InputLeaseManager.

Wraps InputLeaseStore with human intervention detection and emergency
release, implementing the InputLeaseManager protocol from the ADR.

L0 runs at 100Hz, providing:
- Lease acquisition with priority arbitration
- Window focus verification
- Human intervention detection (mouse/keyboard activity)
- Emergency release_all on safety events
"""
from __future__ import annotations

import logging
import time
import uuid

from agent_kernel.protocols import InputLeaseManager as InputLeaseManagerProtocol
from core.types import InputLease
from execution.input_lease import InputLeaseStore

log = logging.getLogger(__name__)


class InputLeaseManagerImpl(InputLeaseManagerProtocol):
    """Concrete L0 InputLeaseManager.

    Manages input leases with human-first intercept. When a physical
    user intervenes (mouse move, key press), all leases are instantly
    released and no new leases are granted for a cooldown period.

    Usage:
        mgr = InputLeaseManagerImpl()
        lease_id = mgr.acquire_lease("combat", 2.0, priority=10)
        # ... use input ...
        mgr.release_lease(lease_id)
    """

    # Cooldown after human intervention before new leases are granted
    HUMAN_INTERVENTION_COOLDOWN_SEC = 2.0

    def __init__(
        self,
        focus_checker: object | None = None,
        human_detector: object | None = None,
    ) -> None:
        self._store = InputLeaseStore()
        self._focus_checker = focus_checker
        self._human_detector = human_detector
        self._last_human_intervention: float = 0.0
        self._emergency = False

    def acquire_lease(self, owner: str, duration_sec: float, priority: int) -> str | None:
        """Acquire an input lease. Returns lease_id or None if denied."""
        now = time.perf_counter()

        if self._emergency:
            log.debug("[L0] Lease denied: emergency stop active")
            return None

        if self._last_human_intervention > 0:
            elapsed = now - self._last_human_intervention
            if elapsed < self.HUMAN_INTERVENTION_COOLDOWN_SEC:
                log.debug("[L0] Lease denied: human cooldown (%.1fs remaining)",
                         self.HUMAN_INTERVENTION_COOLDOWN_SEC - elapsed)
                return None
            self._last_human_intervention = 0.0

        lease_id = f"lease_{uuid.uuid4().hex[:8]}"
        lease = InputLease(
            lease_id=lease_id,
            owner=owner,
            priority=priority,
            created_at=now,
            expires_at=now + duration_sec,
            key_states={},
            mouse_delta=None,
            reason="acquired",
        )
        self._store.add(lease)
        log.debug("[L0] Lease acquired: %s for %s (%.1fs)", lease_id, owner, duration_sec)
        return lease_id

    def release_lease(self, lease_id: str) -> bool:
        """Release a specific lease."""
        removed = self._store.remove(lease_id)
        if removed is not None:
            log.debug("[L0] Lease released: %s", lease_id)
            return True
        return False

    def verify_window_focus(self) -> bool:
        """Check that the target window still has focus."""
        if self._focus_checker is not None:
            try:
                return bool(self._focus_checker.is_target_focused())
            except Exception:
                return False
        return True

    def detect_human_intervention(self) -> bool:
        """Detect physical mouse/keyboard activity from a human user."""
        if self._human_detector is not None:
            try:
                if self._human_detector():
                    self._last_human_intervention = time.perf_counter()
                    log.info("[L0] Human intervention detected — entering cooldown")
                    return True
            except Exception:
                pass
        return False

    def emergency_release_all(self) -> None:
        """Force-release all active leases immediately."""
        released = self._store.clear()
        self._emergency = True
        log.warning("[L0] EMERGENCY RELEASE: %d leases released", len(released))

    def clear_emergency(self) -> None:
        """Clear emergency state (e.g., after user confirmation)."""
        self._emergency = False
        self._last_human_intervention = 0.0
        log.info("[L0] Emergency state cleared")

    @property
    def is_emergency(self) -> bool:
        return self._emergency

    def tick_expiry(self) -> list[str]:
        """Process lease expiry. Call at 100Hz. Returns expired lease IDs."""
        now = time.perf_counter()
        result = self._store.expire_due(now)
        if result.expired_lease_ids:
            log.debug("[L0] Expired %d leases", len(result.expired_lease_ids))
        return result.expired_lease_ids

    def active_lease_count(self) -> int:
        return len(self._store.active_leases_snapshot())

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from core.types import InputLease


DOWN = "DOWN"
UP = "UP"


@dataclass(frozen=True, slots=True)
class LeaseValidationResult:
    valid: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class LeaseExpiryResult:
    expired_lease_ids: list[str] = field(default_factory=list)
    keys_to_release: list[str] = field(default_factory=list)


class InputLeaseStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._leases: dict[str, InputLease] = {}

    def validate(self, lease: InputLease, now: float) -> LeaseValidationResult:
        if not lease.lease_id:
            return LeaseValidationResult(False, "lease_id is required")
        if not lease.owner:
            return LeaseValidationResult(False, "owner is required")
        for key, state in lease.key_states.items():
            if state not in {DOWN, UP}:
                return LeaseValidationResult(False, f"invalid state for {key}: {state}")
            if state == DOWN and lease.expires_at <= now:
                return LeaseValidationResult(False, f"DOWN key {key} has expired lease")
        return LeaseValidationResult(True)

    def add(self, lease: InputLease) -> None:
        with self._lock:
            self._leases[lease.lease_id] = lease

    def remove(self, lease_id: str) -> InputLease | None:
        with self._lock:
            return self._leases.pop(lease_id, None)

    def clear(self) -> list[InputLease]:
        with self._lock:
            leases = list(self._leases.values())
            self._leases.clear()
            return leases

    def expire_due(self, now: float) -> LeaseExpiryResult:
        with self._lock:
            expired_ids = [
                lease_id
                for lease_id, lease in self._leases.items()
                if lease.expires_at <= now and self._has_down_key(lease)
            ]
            if not expired_ids:
                return LeaseExpiryResult()

            expired_leases = [self._leases.pop(lease_id) for lease_id in expired_ids]
            keys_to_release: list[str] = []
            for lease in expired_leases:
                for key, state in lease.key_states.items():
                    if state == DOWN and not self._key_still_held_locked(key):
                        keys_to_release.append(key)

            return LeaseExpiryResult(
                expired_lease_ids=expired_ids,
                keys_to_release=sorted(set(keys_to_release)),
            )

    def active_leases_snapshot(self) -> list[InputLease]:
        with self._lock:
            return list(self._leases.values())

    def active_key_snapshot(self) -> set[str]:
        with self._lock:
            return {
                key
                for lease in self._leases.values()
                for key, state in lease.key_states.items()
                if state == DOWN
            }

    def _key_still_held_locked(self, key: str) -> bool:
        return any(lease.key_states.get(key) == DOWN for lease in self._leases.values())

    def _has_down_key(self, lease: InputLease) -> bool:
        return any(state == DOWN for state in lease.key_states.values())

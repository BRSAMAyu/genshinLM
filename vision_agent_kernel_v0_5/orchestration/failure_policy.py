from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FailurePolicy:
    max_retries: int = 1
    retries_used: int = 0
    on_target_failed: str = "failed"

    def can_retry(self) -> bool:
        return self.retries_used < self.max_retries

    def record_retry(self) -> bool:
        if not self.can_retry():
            return False
        self.retries_used += 1
        return True

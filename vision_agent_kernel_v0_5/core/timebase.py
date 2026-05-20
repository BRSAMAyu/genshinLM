from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


Clock = Callable[[], float]


def perf_counter_seconds() -> float:
    return time.perf_counter()


def perf_counter_ms() -> float:
    return time.perf_counter() * 1000.0


def elapsed_ms(start_seconds: float, end_seconds: float | None = None) -> float:
    end = perf_counter_seconds() if end_seconds is None else end_seconds
    return (end - start_seconds) * 1000.0


@dataclass(slots=True)
class Timebase:
    clock: Clock = field(default=perf_counter_seconds)

    def now(self) -> float:
        return self.clock()

    def now_ms(self) -> float:
        return self.clock() * 1000.0

    def elapsed_ms(self, start_seconds: float) -> float:
        return (self.clock() - start_seconds) * 1000.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    source: str = "paddle"


@dataclass(frozen=True, slots=True)
class OcrConfig:
    language: str = "ch"
    use_gpu: bool = False
    det_limit_side_len: int = 960
    rec_batch_num: int = 6
    enable_mkldnn: bool = True


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    provider: str
    ok: bool
    latency_ms: float = 0.0
    message: str = ""


class OCRProvider(Protocol):
    name: str

    def detect_text(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> list[OcrResult]: ...

    def status(self) -> ProviderStatus: ...

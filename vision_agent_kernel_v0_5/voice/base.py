from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TTSRequest:
    text: str
    voice_id: str = ""
    speed: float = 1.0
    pitch: float = 1.0
    language: str = "zh-CN"
    format: str = "mp3"
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TTSResponse:
    audio_data: bytes
    format: str
    duration_ms: int = 0
    sample_rate: int = 24000
    provider: str = ""
    voice_id: str = ""
    cost_chars: int = 0


@dataclass(frozen=True, slots=True)
class STTRequest:
    audio_data: bytes
    format: str = "wav"
    language: str = "zh-CN"
    sample_rate: int = 16000


@dataclass(frozen=True, slots=True)
class STTResponse:
    text: str
    language: str
    confidence: float
    provider: str = ""
    duration_ms: int = 0


class TTSProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def synthesize(self, request: TTSRequest) -> TTSResponse: ...


class STTProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def recognize(self, request: STTRequest) -> STTResponse: ...

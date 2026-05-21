from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ImageInput:
    data: bytes
    mime_type: str = "image/png"
    frame_id: int | None = None
    roi_id: str = ""


@dataclass(frozen=True, slots=True)
class VisionResult:
    provider: str
    model: str
    text: str
    latency_ms: float
    usage: dict[str, object] = field(default_factory=dict)
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UIGroundingResult:
    provider: str
    query: str
    candidates: list[dict[str, object]]
    latency_ms: float
    raw_text: str = ""


@dataclass(frozen=True, slots=True)
class ScreenStateResult:
    provider: str
    screen_state: str
    confidence: float
    latency_ms: float
    raw_text: str = ""


@dataclass(frozen=True, slots=True)
class VisionProviderStatus:
    provider: str
    ok: bool
    model: str
    base_url: str
    supports_images: bool
    latency_ms: float = 0.0
    message: str = ""


class VisionLLMProvider(Protocol):
    name: str

    def status(self) -> VisionProviderStatus:
        ...

    def describe_image(self, image: ImageInput, prompt: str) -> VisionResult:
        ...

    def ground_ui(self, image: ImageInput, query: str) -> UIGroundingResult:
        ...

    def classify_screen(self, image: ImageInput, candidates: list[str]) -> ScreenStateResult:
        ...

    def explain_failure_with_image(self, summary: dict[str, object], image: ImageInput) -> dict[str, object]:
        ...

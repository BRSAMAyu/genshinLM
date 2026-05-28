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


@dataclass(frozen=True, slots=True)
class VisionBackendStatus:
    backend: str
    ok: bool
    model_id: str
    endpoint: str = ""
    supports_images: bool = True
    latency_ms: float = 0.0
    message: str = ""


@dataclass(frozen=True, slots=True)
class VisionFact:
    fact_id: str
    fact_type: str
    value: object
    confidence: float
    evidence_ref: str = ""
    bbox_norm: tuple[float, float, float, float] | None = None
    source: str = ""


@dataclass(frozen=True, slots=True)
class VisionFactBundle:
    provider: str
    model: str
    screen_state: str = "unknown"
    facts: tuple[VisionFact, ...] = ()
    uncertainty: float = 1.0
    latency_ms: float = 0.0
    raw_text: str = ""


class VisionBackend(Protocol):
    name: str

    def status(self) -> VisionBackendStatus:
        ...

    def extract_facts(self, image: ImageInput, prompt: str = "") -> VisionFactBundle:
        ...


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

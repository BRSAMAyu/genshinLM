from __future__ import annotations


class VoiceAdapter:
    """Placeholder voice adapter.

    The MVP never uses unauthorized voices. It returns text-only output unless
    a future authorized voice pack is explicitly configured.
    """

    def synthesize(self, text: str, voice_id: str | None = None) -> dict[str, str | None]:
        return {"text": text, "voice_id": voice_id, "audio_path": None}

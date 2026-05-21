from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from voice.base import TTSRequest, TTSResponse, STTRequest, STTResponse

_log = logging.getLogger("persona.voice_adapter")


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    voice_id: str = ""
    speed: float = 1.0
    pitch: float = 1.0
    language: str = "zh-CN"
    save_dir: str = ""


class VoiceAdapter:
    """Voice synthesis and recognition adapter.

    Delegates to configured TTS/STT providers (MiniMax, GLM, DashScope).
    Falls back to text-only if no provider is available.
    """

    def __init__(self, config: VoiceConfig | None = None) -> None:
        self._config = config or VoiceConfig()
        self._tts = None
        self._stt = None

    def synthesize(self, text: str, voice_config: VoiceConfig | None = None) -> TTSResponse:
        """Synthesize speech from text. Returns text-only if no TTS provider."""
        cfg = voice_config or self._config
        request = TTSRequest(
            text=text,
            voice_id=cfg.voice_id,
            speed=cfg.speed,
            pitch=cfg.pitch,
            language=cfg.language,
        )

        tts = self._get_tts()
        if tts is None:
            _log.debug("No TTS provider available, returning text-only")
            return TTSResponse(
                audio_data=b"",
                format="text",
                provider="none",
                voice_id=cfg.voice_id,
                cost_chars=0,
            )

        try:
            response = tts.synthesize(request)
            if cfg.save_dir and response.audio_data:
                self._save_audio(response, cfg.save_dir, cfg.voice_id)
            return response
        except Exception as e:
            _log.warning("TTS synthesis failed: %s", e)
            return TTSResponse(
                audio_data=b"",
                format="text",
                provider=tts.name,
                voice_id=cfg.voice_id,
                cost_chars=0,
            )

    def recognize(self, audio_data: bytes, language: str = "zh-CN") -> STTResponse:
        """Recognize speech from audio. Returns empty if no STT provider."""
        stt = self._get_stt()
        if stt is None:
            _log.debug("No STT provider available")
            return STTResponse(text="", language=language, confidence=0.0)

        request = STTRequest(audio_data=audio_data, language=language)
        try:
            return stt.recognize(request)
        except Exception as e:
            _log.warning("STT recognition failed: %s", e)
            return STTResponse(text="", language=language, confidence=0.0)

    def available_tts(self) -> str:
        """Return name of available TTS provider, or 'none'."""
        tts = self._get_tts()
        return tts.name if tts else "none"

    def available_stt(self) -> str:
        """Return name of available STT provider, or 'none'."""
        stt = self._get_stt()
        return stt.name if stt else "none"

    def _get_tts(self):
        if self._tts is None:
            try:
                from voice.tts_provider import get_available_tts
                self._tts = get_available_tts()
            except ImportError:
                self._tts = False
        return self._tts or None

    def _get_stt(self):
        if self._stt is None:
            try:
                from voice.stt_provider import get_available_stt
                self._stt = get_available_stt()
            except ImportError:
                self._stt = False
        return self._stt or None

    def _save_audio(self, response: TTSResponse, save_dir: str, voice_id: str) -> None:
        import time
        path = Path(save_dir)
        path.mkdir(parents=True, exist_ok=True)
        filename = f"tts_{voice_id or 'default'}_{int(time.time())}.{response.format}"
        (path / filename).write_bytes(response.audio_data)
        _log.info("Saved TTS audio to %s", filename)

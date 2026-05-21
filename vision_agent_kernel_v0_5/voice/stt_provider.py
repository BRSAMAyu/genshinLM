from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from voice.base import STTRequest, STTResponse


class _BaseSTT:
    """Shared HTTP STT logic."""

    name: str = ""
    _api_key_env: str = ""
    _default_url: str = ""

    def __init__(self) -> None:
        self._api_key = os.getenv(self._api_key_env, "")
        self._base_url = os.getenv(f"{self._api_key_env}_STT_URL", self._default_url)
        self._timeout = float(os.getenv(f"{self._api_key_env}_STT_TIMEOUT", "30"))

    def available(self) -> bool:
        return bool(self._api_key)

    def recognize(self, request: STTRequest) -> STTResponse:
        raise NotImplementedError


class MiniMaxSTT(_BaseSTT):
    """MiniMax ASR (Automatic Speech Recognition)."""

    name = "minimax"
    _api_key_env = "MINIMAX_API_KEY"
    _default_url = "https://api.minimax.io/v1/audio/transcriptions"

    def recognize(self, request: STTRequest) -> STTResponse:
        import binascii

        boundary = "----SparkleFormBoundary"
        body_parts = []

        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="audio.{request.format}"\r\n'
            f"Content-Type: audio/{request.format}\r\n\r\n".encode()
        )
        body_parts.append(request.audio_data)
        body_parts.append(
            f"\r\n--{boundary}\r\n"
            f'Content-Disposition: form-data; name="language"\r\n\r\n'
            f"{request.language}\r\n"
            f"--{boundary}--\r\n".encode()
        )

        group_id = os.getenv("MINIMAX_GROUP_ID", "")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        if group_id:
            headers["X-Minimax-Group-Id"] = group_id

        body = b"".join(body_parts)
        req = urllib.request.Request(
            self._base_url, data=body, headers=headers, method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        text = data.get("text", "")
        return STTResponse(
            text=text,
            language=request.language,
            confidence=float(data.get("confidence", 0.9)),
            provider=self.name,
        )


class GLMSTT(_BaseSTT):
    """Zhipu (智谱) CogAudio ASR."""

    name = "glm"
    _api_key_env = "GLM_API_KEY"
    _default_url = "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions"

    def recognize(self, request: STTRequest) -> STTResponse:
        import base64

        audio_b64 = base64.b64encode(request.audio_data).decode("ascii")
        payload = {
            "model": "cogaudio",
            "audio": audio_b64,
            "format": request.format,
            "language": request.language,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            self._base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        text = data.get("text", "")
        return STTResponse(
            text=text,
            language=request.language,
            confidence=0.9,
            provider=self.name,
        )


class DashScopeSTT(_BaseSTT):
    """Alibaba DashScope Paraformer / SenseVoice ASR."""

    name = "dashscope"
    _api_key_env = "DASHSCOPE_API_KEY"
    _default_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/audio/asr"

    def recognize(self, request: STTRequest) -> STTResponse:
        import base64

        audio_b64 = base64.b64encode(request.audio_data).decode("ascii")
        payload = {
            "model": "paraformer-v2",
            "input": {
                "audio": audio_b64,
                "format": request.format,
                "sample_rate": request.sample_rate,
            },
            "parameters": {
                "language": request.language,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            self._base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("output", {}).get("results", [])
        text = " ".join(r.get("text", "") for r in results)
        confidence = max((r.get("confidence", 0.9) for r in results), default=0.9)
        return STTResponse(
            text=text,
            language=request.language,
            confidence=float(confidence),
            provider=self.name,
        )


def create_stt_chain() -> list[_BaseSTT]:
    """Create STT providers in priority order."""
    return [MiniMaxSTT(), GLMSTT(), DashScopeSTT()]


def get_available_stt() -> _BaseSTT | None:
    """Return first available STT provider."""
    for provider in create_stt_chain():
        if provider.available():
            return provider
    return None

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from voice.base import TTSRequest, TTSResponse


class _BaseTTS:
    """Shared HTTP TTS logic. Subclasses set endpoint/auth config."""

    name: str = ""
    _api_key_env: str = ""
    _default_url: str = ""
    _default_model: str = ""

    def __init__(self) -> None:
        self._api_key = os.getenv(self._api_key_env, "")
        self._base_url = os.getenv(f"{self._api_key_env}_BASE_URL", self._default_url)
        self._model = os.getenv(f"{self._api_key_env}_MODEL", self._default_model)
        self._timeout = float(os.getenv(f"{self._api_key_env}_TIMEOUT", "30"))

    def available(self) -> bool:
        return bool(self._api_key)

    def synthesize(self, request: TTSRequest) -> TTSResponse:
        raise NotImplementedError


class MiniMaxTTS(_BaseTTS):
    """MiniMax T2A-01 / T2A-02 streaming synthesis."""

    name = "minimax"
    _api_key_env = "MINIMAX_API_KEY"
    _default_url = "https://api.minimax.io/v1/t2a_v2"
    _default_model = "t2a-01"

    # Default Chinese female voice, replaceable via request.voice_id
    DEFAULT_VOICE_ID = "Chinese_Female_Gentle"

    def synthesize(self, request: TTSRequest) -> TTSResponse:
        voice_id = request.voice_id or self.DEFAULT_VOICE_ID
        payload = {
            "model": self._model,
            "text": request.text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": request.speed,
                "pitch": request.pitch,
                "vol": 1.0,
            },
            "audio_setting": {
                "sample_rate": 24000,
                "format": request.format,
                "channel": 1,
            },
        }
        audio_data, resp_data = self._post(payload)
        info = resp_data.get("data", resp_data.get("extra_info", {}))
        return TTSResponse(
            audio_data=audio_data,
            format=request.format,
            duration_ms=int(info.get("duration_ms", 0)),
            sample_rate=24000,
            provider=self.name,
            voice_id=voice_id,
            cost_chars=len(request.text),
        )

    def _post(self, payload: dict) -> tuple[bytes, dict]:
        group_id = os.getenv("MINIMAX_GROUP_ID", "")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if group_id:
            headers["X-Minimax-Group-Id"] = group_id
        req = urllib.request.Request(
            self._base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            raw = resp.read()

        if raw[:1] == b"{":
            data = json.loads(raw)
            hex_audio = data.get("data", {}).get("audio", "")
            import binascii
            audio_bytes = binascii.unhexlify(hex_audio) if hex_audio else b""
            return audio_bytes, data
        return raw, {}


class GLMTTS(_BaseTTS):
    """Zhipu (智谱) CogAudio / glm-4-voice synthesis."""

    name = "glm"
    _api_key_env = "GLM_API_KEY"
    _default_url = "https://open.bigmodel.cn/api/paas/v4/audio/speech"
    _default_model = "cogaudio"

    # GLM uses speaker names, not numeric IDs
    DEFAULT_VOICE = "alloy"

    def synthesize(self, request: TTSRequest) -> TTSResponse:
        payload = {
            "model": self._model,
            "input": request.text,
            "voice": request.voice_id or self.DEFAULT_VOICE,
            "speed": request.speed,
            "response_format": request.format,
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
            audio_data = resp.read()

        return TTSResponse(
            audio_data=audio_data,
            format=request.format,
            sample_rate=24000,
            provider=self.name,
            voice_id=request.voice_id or self.DEFAULT_VOICE,
            cost_chars=len(request.text),
        )


class DashScopeTTS(_BaseTTS):
    """Alibaba DashScope CosyVoice / Sambert synthesis."""

    name = "dashscope"
    _api_key_env = "DASHSCOPE_API_KEY"
    _default_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2audio/generation"
    _default_model = "cosyvoice-v1"

    DEFAULT_VOICE = "longxiaochun"

    def synthesize(self, request: TTSRequest) -> TTSResponse:
        payload = {
            "model": self._model,
            "input": {
                "text": request.text,
            },
            "parameters": {
                "voice": request.voice_id or self.DEFAULT_VOICE,
                "speed": request.speed,
                "pitch": request.pitch,
                "format": request.format,
                "sample_rate": 24000,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        req = urllib.request.Request(
            self._base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        # DashScope returns task ID for async — poll for result
        task_id = data.get("output", {}).get("task_id", "")
        if task_id:
            audio_data = self._poll_task(task_id)
        else:
            audio_url = data.get("output", {}).get("audio_url", "")
            audio_data = self._download(audio_url) if audio_url else b""

        return TTSResponse(
            audio_data=audio_data,
            format=request.format,
            sample_rate=24000,
            provider=self.name,
            voice_id=request.voice_id or self.DEFAULT_VOICE,
            cost_chars=len(request.text),
        )

    def _poll_task(self, task_id: str) -> bytes:
        poll_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        import time
        for _ in range(60):
            req = urllib.request.Request(poll_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            status = result.get("output", {}).get("task_status", "")
            if status == "SUCCEEDED":
                audio_url = result.get("output", {}).get("audio_url", "")
                return self._download(audio_url) if audio_url else b""
            if status in ("FAILED", "CANCELED"):
                break
            time.sleep(0.5)
        return b""

    def _download(self, url: str) -> bytes:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()


def create_tts_chain() -> list[_BaseTTS]:
    """Create TTS providers in priority order: first available wins."""
    providers = [MiniMaxTTS(), GLMTTS(), DashScopeTTS()]
    return providers


def get_available_tts() -> _BaseTTS | None:
    """Return first available TTS provider."""
    for provider in create_tts_chain():
        if provider.available():
            return provider
    return None

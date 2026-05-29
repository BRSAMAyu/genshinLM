"""Local per-user secret storage for Aurora development machines.

On Windows this uses DPAPI via CryptProtectData/CryptUnprotectData so secrets
are bound to the current OS user. Other platforms fall back to a user-only JSON
file and should be treated as development-only storage.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import json
import os
from dataclasses import dataclass
from pathlib import Path


def _default_secret_path() -> Path:
    root = os.getenv("AURORA_SECRET_DIR")
    if root:
        return Path(root) / "secrets.json"
    if os.name == "nt":
        appdata = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Aurora" / "secrets.json"
    return Path.home() / ".config" / "aurora" / "secrets.json"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_available() -> bool:
    return os.name == "nt" and hasattr(ctypes, "windll")


def _dpapi_protect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(data)
    in_blob = _DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Aurora local secret".encode("utf-16-le"),
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(data)
    in_blob = _DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


@dataclass(slots=True)
class LocalSecretStore:
    path: Path = _default_secret_path()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def set(self, name: str, value: str) -> None:
        if not name or not value:
            raise ValueError("secret name and value are required")
        payload = value.encode("utf-8")
        if _dpapi_available():
            encoded = "dpapi:" + base64.b64encode(_dpapi_protect(payload)).decode("ascii")
        else:
            encoded = "plain-dev:" + base64.b64encode(payload).decode("ascii")
        data = self._load()
        data[name] = encoded
        self._save(data)

    def get(self, name: str, default: str = "") -> str:
        encoded = self._load().get(name)
        if not encoded:
            return default
        if encoded.startswith("dpapi:"):
            raw = base64.b64decode(encoded.removeprefix("dpapi:"))
            return _dpapi_unprotect(raw).decode("utf-8")
        if encoded.startswith("plain-dev:"):
            raw = base64.b64decode(encoded.removeprefix("plain-dev:"))
            return raw.decode("utf-8")
        return default

    def delete(self, name: str) -> bool:
        data = self._load()
        existed = name in data
        data.pop(name, None)
        self._save(data)
        return existed


def get_secret(name: str, default: str = "") -> str:
    return LocalSecretStore().get(name, default)

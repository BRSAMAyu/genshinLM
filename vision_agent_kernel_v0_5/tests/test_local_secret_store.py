from __future__ import annotations

from core.local_secret_store import LocalSecretStore


def test_local_secret_store_roundtrip(tmp_path) -> None:
    store = LocalSecretStore(path=tmp_path / "secrets.json")
    store.set("ZHIPU_API_KEY", "test-secret-value")

    assert store.get("ZHIPU_API_KEY") == "test-secret-value"
    raw = (tmp_path / "secrets.json").read_text(encoding="utf-8")
    assert "test-secret-value" not in raw


def test_local_secret_store_delete(tmp_path) -> None:
    store = LocalSecretStore(path=tmp_path / "secrets.json")
    store.set("MINIMAX_API_KEY", "test-secret-value")

    assert store.delete("MINIMAX_API_KEY")
    assert store.get("MINIMAX_API_KEY") == ""

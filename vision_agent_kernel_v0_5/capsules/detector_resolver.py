"""Capsule-aware detector/processor resolver.

Provides a single entry point for consuming code to obtain game-specific
detectors and classifiers *without* importing concrete implementations
directly.  The resolver first checks whether a matching capsule is
registered with the ProviderRegistry; if so, it returns the provider's
wrapped instance.  Otherwise it falls back to a direct import so that
existing code continues to work when the capsule system is not active.

This module is the *only* place outside capsules/ that should import
perception.genshin_* or perception.combat_* modules at runtime.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache for resolved instances (avoids repeated fallback imports)
# ---------------------------------------------------------------------------
_classifier_cache: dict[str, Any] = {}
_combat_detector_cache: dict[str, Any] = {}


def get_screen_classifier(capsule_id: str = "genshin") -> Any:
    """Return a screen classifier instance, preferring capsule provider.

    Resolution order:
      1. ProviderRegistry[capsule_id]["screen_classifier"] -> provider._classifier
      2. Direct import fallback: perception.genshin_screen_classifier.GenshinScreenClassifier
    """
    if capsule_id in _classifier_cache:
        return _classifier_cache[capsule_id]

    # --- Try capsule provider registry ---
    provider = _get_provider(capsule_id, "screen_classifier")
    if provider is not None:
        # Providers wrap the underlying classifier in provider._classifier
        raw = getattr(provider, "_classifier", None)
        if raw is not None:
            _classifier_cache[capsule_id] = raw
            log.debug("Resolved screen_classifier from capsule '%s' provider", capsule_id)
            return raw

    # --- Fallback: direct import ---
    try:
        from perception.genshin_screen_classifier import GenshinScreenClassifier

        instance = GenshinScreenClassifier()
        _classifier_cache[capsule_id] = instance
        log.debug("Resolved screen_classifier via direct import (capsule '%s' not active)", capsule_id)
        return instance
    except Exception as exc:
        log.warning("Failed to resolve screen_classifier: %s", exc)
        return None


def get_combat_detector(capsule_id: str = "genshin") -> Any:
    """Return a combat detector instance, preferring capsule provider.

    Resolution order:
      1. ProviderRegistry[capsule_id]["combat_detector"] (if registered)
      2. Direct import fallback: perception.genshin_combat_detector.GenshinCombatDetector
    """
    if capsule_id in _combat_detector_cache:
        return _combat_detector_cache[capsule_id]

    # --- Try capsule provider registry ---
    provider = _get_provider(capsule_id, "combat_detector")
    if provider is not None:
        raw = getattr(provider, "_detector", None)
        if raw is not None:
            _combat_detector_cache[capsule_id] = raw
            log.debug("Resolved combat_detector from capsule '%s' provider", capsule_id)
            return raw

    # --- Fallback: direct import ---
    try:
        from perception.genshin_combat_detector import GenshinCombatDetector

        instance = GenshinCombatDetector()
        _combat_detector_cache[capsule_id] = instance
        log.debug("Resolved combat_detector via direct import (capsule '%s' not active)", capsule_id)
        return instance
    except Exception as exc:
        log.warning("Failed to resolve combat_detector: %s", exc)
        return None


def _get_provider(capsule_id: str, provider_type: str) -> Any | None:
    """Look up a provider from the global provider registry (lazy import)."""
    try:
        from capsules.provider_registry import provider_registry

        return provider_registry.get_provider(capsule_id, provider_type)
    except Exception:
        return None


def clear_cache() -> None:
    """Clear cached instances (useful for testing or capsule re-registration)."""
    _classifier_cache.clear()
    _combat_detector_cache.clear()

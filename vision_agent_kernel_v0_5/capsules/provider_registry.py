from __future__ import annotations

import importlib
import logging
import threading
from typing import Any, Dict

from capsules.domain_protocols import ProviderHealth

logger = logging.getLogger("provider_registry")


class ProviderRegistry:
    """Manages capsule game domain providers lifecycle: register, retrieve, unregister."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._registry: Dict[str, Dict[str, Any]] = {}

    def register_providers(self, capsule_id: str, providers_map: Dict[str, str]) -> None:
        """Dynamically load and instantiate providers declared in the manifest.

        Args:
            capsule_id: The unique capsule identifier.
            providers_map: Map of provider_type (e.g. 'screen_classifier') to import path string.
        """
        with self._lock:
            if capsule_id in self._registry:
                logger.warning("Providers for capsule '%s' are already registered. Re-registering.", capsule_id)
                self.unregister_providers(capsule_id)

            instantiated: Dict[str, Any] = {}
            try:
                for p_type, p_path in providers_map.items():
                    logger.debug("Loading provider '%s' from path '%s'", p_type, p_path)
                    try:
                        cls = self._load_class(p_path)
                        instance = cls()
                        instantiated[p_type] = instance
                    except Exception as e:
                        raise ImportError(f"Failed to load class '{p_path}' for type '{p_type}': {e}") from e

                # All successfully loaded
                self._registry[capsule_id] = instantiated
                logger.info("Successfully registered %d providers for capsule '%s'", len(instantiated), capsule_id)

            except Exception:
                # Cleanup instantiated providers on failure
                logger.exception("Provider registration failed for capsule '%s', rolling back", capsule_id)
                self.unregister_providers(capsule_id)
                raise

    def get_provider(self, capsule_id: str, provider_type: str) -> Any | None:
        """Retrieve a specific domain provider for a capsule.

        Args:
            capsule_id: The capsule identifier.
            provider_type: The type of provider (e.g., 'screen_classifier').
        """
        with self._lock:
            return self._registry.get(capsule_id, {}).get(provider_type)

    def unregister_providers(self, capsule_id: str) -> None:
        """Unregister and clean up all domain providers for a capsule."""
        with self._lock:
            removed = self._registry.pop(capsule_id, None)
            if removed:
                logger.info("Unregistered %d providers for capsule '%s'", len(removed), capsule_id)

    def list_capsules(self) -> list[str]:
        """List all capsule IDs that have registered providers."""
        with self._lock:
            return sorted(self._registry.keys())

    def health(self, capsule_id: str) -> Dict[str, ProviderHealth]:
        """Query health of all registered providers in a capsule."""
        with self._lock:
            results: Dict[str, ProviderHealth] = {}
            providers = self._registry.get(capsule_id, {})
            for p_type, p_instance in providers.items():
                health_fn = getattr(p_instance, "health", None)
                if callable(health_fn):
                    try:
                        results[p_type] = health_fn()
                    except Exception as e:
                        results[p_type] = ProviderHealth("error", str(e))
                else:
                    results[p_type] = ProviderHealth("ok", "No health check method found")
            return results

    def _load_class(self, path_str: str) -> Any:
        module_path, _, class_name = path_str.partition(":")
        if not module_path or not class_name:
            raise ValueError(f"Invalid provider class path structure: '{path_str}'. Must be 'module:ClassName'")
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)


# Global provider registry instance
provider_registry = ProviderRegistry()

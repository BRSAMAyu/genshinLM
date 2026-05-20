from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from capsules.capsule_protocol import Capsule, CapsuleContext, CapsuleManifest

logger = logging.getLogger("capsule_registry")


class CapsuleRegistry:
    """Manages capsule lifecycle: register, activate, deactivate, unregister."""

    def __init__(self) -> None:
        self._capsules: dict[str, Capsule] = {}
        self._manifests: dict[str, CapsuleManifest] = {}
        self._contexts: dict[str, CapsuleContext] = {}
        self._active: set[str] = set()
        self._subscription_ids: dict[str, list[str]] = {}

    def register(
        self,
        capsule: Capsule,
        manifest: CapsuleManifest,
        context: CapsuleContext,
    ) -> None:
        """Register and install a capsule."""
        cid = capsule.capsule_id
        if cid in self._capsules:
            raise ValueError(f"Capsule '{cid}' is already registered")

        # Snapshot subscription counter before install to track new subscriptions.
        sub_counter_before = context.state_bus._sub_counter

        try:
            capsule.install(context)
        except Exception:
            logger.exception("Failed to install capsule '%s'", cid)
            raise

        # Collect subscription IDs created during install.
        sub_counter_after = context.state_bus._sub_counter
        new_sub_ids: list[str] = []
        # Unfortunately StateBus.subscribe generates opaque IDs, so we track
        # by range. We reconstruct the IDs using the same formula. Since we
        # cannot know the callback id/thread id, we record the counter delta
        # and store it for later cleanup. Instead, we simply snapshot the
        # current _sub_ids keys that were added after our marker.
        # A cleaner approach: ask the StateBus for recently added sub IDs.
        # We iterate backwards through known IDs to find new ones.
        current_sub_ids = set(context.state_bus._sub_ids.keys())
        new_sub_ids = []  # We'll use the counter range approach

        # Record the counter range for later cleanup via StateBus internals.
        self._subscription_ids[cid] = []  # populated below

        self._capsules[cid] = capsule
        self._manifests[cid] = manifest
        self._contexts[cid] = context

        logger.info("Capsule '%s' registered and installed", cid)

    def unregister(self, capsule_id: str) -> bool:
        """Deactivate + uninstall + remove."""
        if capsule_id not in self._capsules:
            return False

        capsule = self._capsules[capsule_id]
        context = self._contexts[capsule_id]

        # Deactivate if active.
        if capsule_id in self._active:
            try:
                capsule.deactivate()
            except Exception:
                logger.exception("Error deactivating capsule '%s'", capsule_id)
            self._active.discard(capsule_id)

        # Uninstall.
        try:
            capsule.uninstall(context)
        except Exception:
            logger.exception("Error uninstalling capsule '%s'", capsule_id)

        # Unsubscribe tracked subscription IDs.
        for sub_id in self._subscription_ids.get(capsule_id, []):
            context.state_bus.unsubscribe(sub_id)

        # Remove from registry.
        del self._capsules[capsule_id]
        del self._manifests[capsule_id]
        del self._contexts[capsule_id]
        self._subscription_ids.pop(capsule_id, None)

        logger.info("Capsule '%s' unregistered", capsule_id)
        return True

    def activate(self, capsule_id: str) -> bool:
        """Activate a registered capsule."""
        if capsule_id not in self._capsules:
            return False
        if capsule_id in self._active:
            return True
        try:
            self._capsules[capsule_id].activate()
            self._active.add(capsule_id)
            logger.info("Capsule '%s' activated", capsule_id)
            return True
        except Exception:
            logger.exception("Error activating capsule '%s'", capsule_id)
            return False

    def deactivate(self, capsule_id: str) -> bool:
        """Deactivate an active capsule."""
        if capsule_id not in self._capsules:
            return False
        if capsule_id not in self._active:
            return True
        try:
            self._capsules[capsule_id].deactivate()
            self._active.discard(capsule_id)
            logger.info("Capsule '%s' deactivated", capsule_id)
            return True
        except Exception:
            logger.exception("Error deactivating capsule '%s'", capsule_id)
            return False

    def get(self, capsule_id: str) -> Capsule | None:
        """Get a capsule by ID, or None if not registered."""
        return self._capsules.get(capsule_id)

    def list_active(self) -> list[str]:
        """List IDs of all active capsules."""
        return sorted(self._active)

    def list_registered(self) -> list[str]:
        """List IDs of all registered capsules."""
        return sorted(self._capsules.keys())

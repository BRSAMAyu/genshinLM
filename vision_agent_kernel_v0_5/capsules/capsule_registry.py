from __future__ import annotations

import logging
from pathlib import Path
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
        self._manifest_paths: dict[str, Path] = {}
        self._slot_names: dict[str, list[str]] = {}
        self._skill_names: dict[str, list[str]] = {}
        self._transition_specs: dict[str, list[tuple[object, object, object]]] = {}
        self._post_processors: dict[str, list[object]] = {}

    def register(
        self,
        capsule: Capsule,
        manifest: CapsuleManifest,
        context: CapsuleContext,
        manifest_path: str | Path | None = None,
    ) -> None:
        """Register and install a capsule."""
        cid = capsule.capsule_id
        if cid in self._capsules:
            raise ValueError(f"Capsule '{cid}' is already registered")
        if manifest.capsule_id != cid:
            raise ValueError(f"Manifest capsule_id '{manifest.capsule_id}' does not match capsule '{cid}'")
        if manifest_path is not None:
            self._validate_manifest_resources(manifest, Path(manifest_path))

        subscription_ids_before = set(context.state_bus.subscription_ids())
        slot_names_before = set(context.state_bus.registered_slot_names())
        skill_names_before = self._skill_names_snapshot(context)
        transition_specs_before = self._transition_specs_snapshot(context)
        processors_before = self._post_processors_snapshot(context)

        # Load providers if declared in manifest.providers
        if hasattr(manifest, "providers") and manifest.providers:
            from capsules.provider_registry import provider_registry
            try:
                provider_registry.register_providers(cid, manifest.providers)
            except Exception:
                logger.exception("Failed to load providers for capsule '%s'", cid)
                raise

        try:
            capsule.install(context)
        except Exception:
            # Rollback providers
            if hasattr(manifest, "providers") and manifest.providers:
                from capsules.provider_registry import provider_registry
                provider_registry.unregister_providers(cid)
            for sub_id in set(context.state_bus.subscription_ids()) - subscription_ids_before:
                context.state_bus.unsubscribe(sub_id)
            self._cleanup_install_delta(
                cid,
                context,
                slot_names_before,
                skill_names_before,
                transition_specs_before,
                processors_before,
            )
            logger.exception("Failed to install capsule '%s'", cid)
            raise

        subscription_ids_after = set(context.state_bus.subscription_ids())
        self._subscription_ids[cid] = sorted(subscription_ids_after - subscription_ids_before)
        self._slot_names[cid] = sorted(set(context.state_bus.registered_slot_names()) - slot_names_before)
        self._skill_names[cid] = sorted(self._skill_names_snapshot(context) - skill_names_before)
        self._transition_specs[cid] = sorted(
            self._transition_specs_snapshot(context) - transition_specs_before,
            key=lambda item: (str(item[0]), str(item[1]), str(item[2])),
        )
        processor_ids_before = {id(processor) for processor in processors_before}
        self._post_processors[cid] = [
            processor for processor in self._post_processors_snapshot(context)
            if id(processor) not in processor_ids_before
        ]

        self._capsules[cid] = capsule
        self._manifests[cid] = manifest
        self._contexts[cid] = context
        if manifest_path is not None:
            self._manifest_paths[cid] = Path(manifest_path)

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

        # Teardown providers
        from capsules.provider_registry import provider_registry
        provider_registry.unregister_providers(capsule_id)

        # Uninstall.
        try:
            capsule.uninstall(context)
        except Exception:
            logger.exception("Error uninstalling capsule '%s'", capsule_id)

        # Unsubscribe tracked subscription IDs.
        for sub_id in self._subscription_ids.get(capsule_id, []):
            context.state_bus.unsubscribe(sub_id)

        for processor in self._post_processors.get(capsule_id, []):
            self._remove_post_processor(context, processor)

        for skill_name in self._skill_names.get(capsule_id, []):
            self._unregister_skill(context, skill_name)

        for from_state, to_state, condition in self._transition_specs.get(capsule_id, []):
            self._unregister_transition(context, from_state, to_state, condition)

        for slot_name in self._slot_names.get(capsule_id, []):
            context.state_bus.unregister_slot(slot_name)

        # Remove from registry.
        del self._capsules[capsule_id]
        del self._manifests[capsule_id]
        del self._contexts[capsule_id]
        self._subscription_ids.pop(capsule_id, None)
        self._manifest_paths.pop(capsule_id, None)
        self._slot_names.pop(capsule_id, None)
        self._skill_names.pop(capsule_id, None)
        self._transition_specs.pop(capsule_id, None)
        self._post_processors.pop(capsule_id, None)

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

    def manifest(self, capsule_id: str) -> CapsuleManifest | None:
        """Return the registered manifest for planner/catalog consumers."""
        return self._manifests.get(capsule_id)

    def list_manifests(self) -> list[CapsuleManifest]:
        """Return registered manifests sorted by capsule id."""
        return [self._manifests[cid] for cid in self.list_registered()]

    def skill_catalog(self) -> list[dict[str, object]]:
        """Flatten capsule skill declarations into planner-friendly catalog rows."""
        rows: list[dict[str, object]] = []
        for cid in self.list_registered():
            manifest = self._manifests[cid]
            for skill in manifest.skills:
                rows.append(
                    {
                        "capsule_id": manifest.capsule_id,
                        "skill_id": skill.skill_id,
                        "kind": skill.kind,
                        "capabilities": list(skill.capabilities),
                        "resources": list(skill.resources),
                        "verifiers": list(skill.verifiers),
                        "planner_tags": list(skill.planner_tags),
                    }
                )
        return rows

    def _validate_manifest_resources(self, manifest: CapsuleManifest, manifest_path: Path) -> None:
        for resource_id, path in manifest.resource_paths(manifest_path).items():
            resource = next(res for res in manifest.resources if res.resource_id == resource_id)
            if not path.exists() and not resource.optional:
                raise FileNotFoundError(
                    f"Capsule '{manifest.capsule_id}' resource '{resource_id}' not found: {path}"
                )

    def _cleanup_install_delta(
        self,
        capsule_id: str,
        context: CapsuleContext,
        slot_names_before: set[str],
        skill_names_before: set[str],
        transition_specs_before: set[tuple[object, object, object]],
        processors_before: list[object],
    ) -> None:
        processor_ids_before = {id(processor) for processor in processors_before}
        for processor in self._post_processors_snapshot(context):
            if id(processor) not in processor_ids_before:
                self._remove_post_processor(context, processor)
        for skill_name in self._skill_names_snapshot(context) - skill_names_before:
            self._unregister_skill(context, skill_name)
        for from_state, to_state, condition in self._transition_specs_snapshot(context) - transition_specs_before:
            self._unregister_transition(context, from_state, to_state, condition)
        for slot_name in set(context.state_bus.registered_slot_names()) - slot_names_before:
            context.state_bus.unregister_slot(slot_name)
        self._slot_names.pop(capsule_id, None)
        self._skill_names.pop(capsule_id, None)
        self._transition_specs.pop(capsule_id, None)
        self._post_processors.pop(capsule_id, None)

    def _skill_names_snapshot(self, context: CapsuleContext) -> set[str]:
        method = getattr(context.orchestrator, "skill_names", None)
        if callable(method):
            try:
                values = method()
                if isinstance(values, (list, tuple, set)):
                    return {str(value) for value in values}
            except Exception:
                pass
        skills = getattr(context.orchestrator, "_skills", None)
        if isinstance(skills, dict):
            return {str(key) for key in skills.keys()}
        return set()

    def _transition_specs_snapshot(self, context: CapsuleContext) -> set[tuple[object, object, object]]:
        method = getattr(context.orchestrator, "custom_transitions_snapshot", None)
        if callable(method):
            try:
                values = method()
                if isinstance(values, (list, tuple, set)):
                    return {tuple(value) for value in values}
            except Exception:
                pass
        graph = getattr(context.orchestrator, "_graph", None)
        transitions = getattr(graph, "_custom_transitions", None)
        if isinstance(transitions, list):
            return {tuple(value) for value in transitions}
        return set()

    def _post_processors_snapshot(self, context: CapsuleContext) -> list[object]:
        method = getattr(context.pipeline, "post_processors_snapshot", None)
        if callable(method):
            try:
                values = method()
                if isinstance(values, list):
                    return list(values)
            except Exception:
                pass
        processors = getattr(context.pipeline, "_post_processors", None)
        if isinstance(processors, list):
            return list(processors)
        return []

    def _unregister_skill(self, context: CapsuleContext, skill_name: str) -> None:
        method = getattr(context.orchestrator, "unregister_skill", None)
        if callable(method):
            try:
                method(skill_name)
            except Exception:
                logger.exception("Failed to unregister skill '%s'", skill_name)

    def _unregister_transition(
        self,
        context: CapsuleContext,
        from_state: object,
        to_state: object,
        condition: object,
    ) -> None:
        method = getattr(context.orchestrator, "unregister_transition", None)
        if callable(method):
            try:
                method(from_state, to_state, condition)
            except Exception:
                logger.exception("Failed to unregister transition '%s' -> '%s'", from_state, to_state)

    def _remove_post_processor(self, context: CapsuleContext, processor: object) -> None:
        method = getattr(context.pipeline, "remove_post_processor", None)
        if callable(method):
            try:
                method(processor)
            except Exception:
                logger.exception("Failed to remove capsule post-processor")

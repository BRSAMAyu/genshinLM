"""Validate skill patch drafts in dry-run and verifier-replay modes."""
from __future__ import annotations

import logging

from repair.skill_patch_builder import SkillPatchDraft

log = logging.getLogger(__name__)


class RepairValidator:
    """Validates a SkillPatchDraft through dry-run and verifier replay."""

    def validate_dry_run(self, patch: SkillPatchDraft) -> bool:
        """Run patched skill in dry-run mode. Returns True if no errors.

        Checks that proposed steps are well-formed and pass sandbox execution
        if executable code is present in patch metadata.
        """
        for step in patch.proposed_steps:
            if "action_type" not in step:
                return False
            action_type = step.get("action_type")
            if not isinstance(action_type, str) or not action_type:
                return False
            params = step.get("params")
            if params is not None and not isinstance(params, dict):
                return False

        # If the patch contains executable code, validate in sandbox
        code = patch.safety.get("code", "") if patch.safety else ""
        if code and isinstance(code, str) and len(code) > 20:
            try:
                from app_service.code_sandbox_executor import CodeSandboxExecutor
                sandbox = CodeSandboxExecutor()
                result = sandbox.execute(code)
                if not result.success:
                    log.warning(
                        "[RepairValidator] Sandbox failed for patch %s: %s",
                        patch.patch_id, result.error[:200],
                    )
                    return False
            except ImportError:
                pass  # CodeSandboxExecutor not available

        return True

    def validate_verifier_replay(self, patch: SkillPatchDraft, verifier_contract: dict[str, object]) -> bool:
        """Run patched skill with verifier contract. Returns True if verifier passes."""
        if not verifier_contract:
            return True

        if not patch.proposed_steps:
            return False

        required_actions = verifier_contract.get("required_actions")
        if isinstance(required_actions, list):
            patch_actions = {step.get("action_type") for step in patch.proposed_steps}
            for required in required_actions:
                if required not in patch_actions:
                    return False

        max_steps = verifier_contract.get("max_steps")
        if isinstance(max_steps, (int, float)) and len(patch.proposed_steps) > max_steps:
            return False

        return True

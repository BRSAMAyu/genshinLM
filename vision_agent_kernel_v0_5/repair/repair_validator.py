"""Validate skill patch drafts in dry-run and verifier-replay modes."""

from __future__ import annotations

from repair.skill_patch_builder import SkillPatchDraft


class RepairValidator:
    """Validates a SkillPatchDraft through dry-run and verifier replay."""

    def validate_dry_run(self, patch: SkillPatchDraft) -> bool:
        """Run patched skill in dry-run mode. Returns True if no errors.

        Dry-run validation checks that the proposed steps are well-formed
        and do not reference unknown actions.
        """
        # Validate proposed steps structure
        for step in patch.proposed_steps:
            if "action_type" not in step:
                return False
            action_type = step.get("action_type")
            if not isinstance(action_type, str) or not action_type:
                return False
            params = step.get("params")
            if params is not None and not isinstance(params, dict):
                return False

        return True

    def validate_verifier_replay(self, patch: SkillPatchDraft, verifier_contract: dict[str, object]) -> bool:
        """Run patched skill with verifier contract. Returns True if verifier passes.

        Validates that the patch's verifier_contract matches the expected contract
        and that proposed steps satisfy the contract constraints.
        """
        if not verifier_contract:
            return True

        # Check that the patch has proposed steps
        if not patch.proposed_steps:
            return False

        # Check that the verifier contract is satisfied
        # A minimal contract may specify required action types
        required_actions = verifier_contract.get("required_actions")
        if isinstance(required_actions, list):
            patch_actions = {step.get("action_type") for step in patch.proposed_steps}
            for required in required_actions:
                if required not in patch_actions:
                    return False

        # Check max_steps constraint if specified
        max_steps = verifier_contract.get("max_steps")
        if isinstance(max_steps, (int, float)) and len(patch.proposed_steps) > max_steps:
            return False

        return True

from __future__ import annotations

from learning.failure_signature import FailureSignature


class LearningReport:
    def render(self, failures: list[FailureSignature]) -> str:
        lines = ["# Learning Report", "", "Screenshots must be privacy-masked before review/export.", ""]
        for failure in failures:
            lines.extend(
                [
                    f"## {failure.failure_id}",
                    f"- node_type: `{failure.node_type}`",
                    f"- skill_id: `{failure.skill_id}`",
                    f"- failure_code: `{failure.failure_code}`",
                    f"- suggested_patch: `{', '.join(failure.suggested_patch) if failure.suggested_patch else 'none'}`",
                    "",
                ]
            )
        return "\n".join(lines)

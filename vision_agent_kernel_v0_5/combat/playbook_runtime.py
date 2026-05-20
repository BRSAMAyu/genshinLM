from __future__ import annotations

from typing import Any

from combat.combat_context import CombatContext


class CombatPlaybookRuntime:
    REQUIRED_NODES = {"maintain_lock", "dodge_if_danger"}
    SUPPORTED_TYPES = {
        "condition",
        "action",
        "reflex",
        "verification",
        "guard",
        "checkpoint",
        "branch",
        "fallback",
    }

    def validate(self, playbook: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        nodes = {node.get("node_id") for node in playbook.get("nodes", [])}
        if not nodes:
            errors.append("playbook must contain nodes")
        for required in self.REQUIRED_NODES:
            if required not in nodes:
                errors.append(f"playbook must contain {required} node")
        if "max_retries" not in playbook.get("retry", {}):
            errors.append("playbook retry.max_retries is required")
        for node in playbook.get("nodes", []):
            node_type = node.get("type")
            if node_type not in self.SUPPORTED_TYPES:
                errors.append(f"unsupported node type: {node_type}")
            if node.get("node_id") == "dodge_if_danger" and node_type != "reflex":
                errors.append("dodge_if_danger must be a reflex node")
        for edge in playbook.get("edges", []):
            if len(edge) != 2 or edge[0] not in nodes or edge[1] not in nodes:
                errors.append(f"invalid edge: {edge}")
        return {"ok": not errors, "errors": errors, "simulation": "PASS" if not errors else "BLOCKED"}

    def dry_run(self, playbook: dict[str, Any]) -> dict[str, Any]:
        validation = self.validate(playbook)
        if not validation["ok"]:
            return {"ok": False, "trace": [], "validation": validation}
        trace = [node["node_id"] for node in sorted(playbook["nodes"], key=lambda item: item.get("priority", 0), reverse=True)]
        return {"ok": True, "trace": trace, "validation": validation}

    def tick(
        self,
        playbook: dict[str, Any],
        context: CombatContext,
        danger_score: float,
        checkpoint: str | None = None,
    ) -> dict[str, Any]:
        validation = self.validate(playbook)
        if not validation["ok"]:
            return {"ok": False, "node": None, "action": "blocked", "validation": validation}
        node_id = "maintain_lock"
        action = "track_target"
        interrupted = False
        resume_from = checkpoint or "maintain_lock"
        if danger_score >= 0.8:
            node_id = "dodge_if_danger"
            action = "interrupt_and_dodge"
            interrupted = True
        elif context.hp_ratio < 0.35:
            node_id = "heal_if_low_hp"
            action = "heal_if_low_hp"
        elif context.target_visible and danger_score < 0.45:
            node_id = "burst_if_safe"
            action = "burst_if_safe"
        elif context.target_visible:
            node_id = "attack_if_safe"
            action = "attack_if_safe"
        return {
            "ok": True,
            "node": node_id,
            "action": action,
            "interrupted": interrupted,
            "resume_from_checkpoint": resume_from,
            "fallback": playbook.get("fallback", "fallback_basic_loop"),
        }

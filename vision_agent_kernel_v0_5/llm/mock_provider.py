from __future__ import annotations

from llm.provider_base import PlannerProposal


class MockProvider:
    name = "mock"

    def plan(self, goal: str, skills: list[dict], persona_id: str) -> PlannerProposal:
        skill_ids = [str(skill["skill_id"]) for skill in skills[:3]]
        task_spec = {
            "task_id": "mock_planned_task",
            "goal": goal,
            "persona_id": persona_id,
            "skill_chain": skill_ids,
            "max_duration_sec": 60,
            "max_retries": 2,
            "requires_user_confirmation": True,
            "input_mode": "dry-run",
            "tools": ["list_skills", "create_task_spec", "select_skill_chain"],
            "graph": {
                "nodes": ["LOAD_TASK", "ACQUIRE_TARGET", "EXECUTE_SKILL_CHAIN", "VERIFY_SUCCESS", "COMPLETE"],
                "edges": [
                    ["LOAD_TASK", "ACQUIRE_TARGET"],
                    ["ACQUIRE_TARGET", "EXECUTE_SKILL_CHAIN"],
                    ["EXECUTE_SKILL_CHAIN", "VERIFY_SUCCESS"],
                    ["VERIFY_SUCCESS", "COMPLETE"],
                ],
            },
        }
        return PlannerProposal(
            provider=self.name,
            task_spec=task_spec,
            skill_chain=skill_ids,
            risks=["Real execution requires user confirmation.", "The agent pauses if the target window loses focus."],
            usage={"estimated_tokens": 0, "cost_guard": "mock"},
        )

    def explain_failure(self, summary: dict) -> dict:
        reason = summary.get("failure_code") or summary.get("active_interrupt") or "unknown"
        return {
            "user_friendly_summary": f"The run did not complete. The likely reason is {reason}. I suggest checking focus, ROI, and target visibility first.",
            "technical_summary": f"Failure summary: {summary}",
            "suggested_next_steps": ["Check calibration profile", "Run dry-run replay", "Inspect target_visible checkpoints"],
            "possible_skill_patch": {
                "requires_user_confirmation": True,
                "suggestion": "Add wait_visual_trigger before the next action segment.",
            },
        }

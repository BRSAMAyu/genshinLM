from __future__ import annotations

import json

from llm.http_provider import ChatHTTPClient
from llm.provider_base import PlannerProposal
from llm.tool_schema import ALLOWED_TOOLS


class GLMProvider:
    name = "glm"

    def __init__(self) -> None:
        self._client = ChatHTTPClient(
            api_key_env="GLM_API_KEY",
            default_base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
            default_model="glm-5.1",
            base_url_env="GLM_BASE_URL",
            model_env="GLM_MODEL",
            timeout_env="GLM_TIMEOUT_SEC",
            retry_env="GLM_RETRIES",
        )

    def plan(self, goal: str, skills: list[dict], persona_id: str) -> PlannerProposal:
        task_spec, usage = self._client.chat_json(
            _system_prompt(),
            _user_prompt(goal, skills, persona_id),
            temperature=0.2,
            max_tokens=1600,
        )
        skill_chain = [str(item) for item in task_spec.get("skill_chain", [])]
        return PlannerProposal(self.name, task_spec, skill_chain, ["Real execution requires user confirmation."], usage=usage)

    def explain_failure(self, summary: dict) -> dict:
        payload, usage = self._client.chat_json(
            "Return strict JSON with user_friendly_summary, technical_summary, suggested_next_steps, possible_skill_patch. Do not modify files.",
            json.dumps({"summary": summary}, ensure_ascii=False),
            temperature=0.2,
            max_tokens=1000,
        )
        payload.setdefault("usage", usage)
        return payload


def _system_prompt() -> str:
    return (
        "You are a safe local vision-agent planner. Return strict JSON only. "
        "You may only use whitelisted tools. Do not output raw input commands, direct clicks, direct key presses, online game automation, boosting, anti-cheat bypass, memory reading, or driver-level actions. "
        "The TaskSpec must require user confirmation and default to dry-run."
    )


def _user_prompt(goal: str, skills: list[dict], persona_id: str) -> str:
    return json.dumps(
        {
            "goal": goal,
            "persona_id": persona_id,
            "available_skills": skills,
            "allowed_tools": sorted(ALLOWED_TOOLS),
            "required_schema": {
                "task_id": "string",
                "goal": "string",
                "persona_id": "string",
                "skill_chain": ["skill_id"],
                "max_duration_sec": 60,
                "max_retries": 2,
                "requires_user_confirmation": True,
                "input_mode": "dry-run",
                "tools": ["list_skills", "create_task_spec", "select_skill_chain"],
                "graph": {"nodes": ["LOAD_TASK", "COMPLETE"], "edges": [["LOAD_TASK", "COMPLETE"]]},
            },
        },
        ensure_ascii=False,
    )

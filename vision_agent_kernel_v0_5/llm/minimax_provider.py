from __future__ import annotations

import json

from llm.glm_provider import _system_prompt, _user_prompt
from llm.http_provider import ChatHTTPClient
from llm.provider_base import PlannerProposal


class MiniMaxProvider:
    name = "minimax"

    def __init__(self) -> None:
        self._client = ChatHTTPClient(
            api_key_env="MINIMAX_API_KEY",
            default_base_url="https://api.minimax.io/v1/text/chatcompletion_v2",
            default_model="MiniMax-M2.7",
            base_url_env="MINIMAX_BASE_URL",
            model_env="MINIMAX_MODEL",
            timeout_env="MINIMAX_TIMEOUT_SEC",
            retry_env="MINIMAX_RETRIES",
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

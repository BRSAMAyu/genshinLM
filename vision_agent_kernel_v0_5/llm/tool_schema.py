from __future__ import annotations


ALLOWED_TOOLS = {
    "list_skills",
    "describe_skill",
    "create_task_spec",
    "select_skill_chain",
    "modify_task",
    "explain_failure",
    "summarize_run",
    "suggest_skill_patch",
    "suggest_roi_adjustment",
    "pause_agent",
    "emergency_stop",
    "resolve_resource",
    "list_sources",
    "rank_routes",
    "build_mission_queue",
}

FORBIDDEN_TOOLS = {
    "raw_key_input",
    "raw_mouse_input",
    "direct_click",
    "direct_press_key",
    "bypass_safety",
}


def tool_allowed(name: str) -> bool:
    return name in ALLOWED_TOOLS and name not in FORBIDDEN_TOOLS

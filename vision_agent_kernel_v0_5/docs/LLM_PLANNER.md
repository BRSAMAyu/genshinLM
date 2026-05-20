# LLM Planner

The planner converts a natural language goal into a safe `TaskSpec` proposal. It never controls low-level input directly.

## Providers

Default provider:

- `mock`

Optional real providers:

- `glm`
- `minimax`

## Configuration

Set API keys through environment variables only. Do not commit keys.

```powershell
$env:GLM_API_KEY="..."
$env:MINIMAX_API_KEY="..."
```

Optional provider settings:

```powershell
$env:GLM_MODEL="glm-5.1"
$env:GLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4/chat/completions"
$env:GLM_TIMEOUT_SEC="20"
$env:GLM_RETRIES="1"

$env:MINIMAX_MODEL="MiniMax-M2.7"
$env:MINIMAX_BASE_URL="https://api.minimax.io/v1/text/chatcompletion_v2"
$env:MINIMAX_TIMEOUT_SEC="20"
$env:MINIMAX_RETRIES="1"
```

If a real provider is unavailable, the planner falls back to `mock` and returns `provider_error`.

## Request Guard

`LLMRequestGuard` enforces:

- max calls per minute
- max calls per task
- estimated token/cost budget
- provider error isolation
- failover to mock

## Tool Enforcement

Allowed tools:

- `list_skills`
- `describe_skill`
- `create_task_spec`
- `select_skill_chain`
- `modify_task`
- `explain_failure`
- `summarize_run`
- `suggest_skill_patch`
- `suggest_roi_adjustment`
- `pause_agent`
- `emergency_stop`

Forbidden tools:

- `raw_key_input`
- `raw_mouse_input`
- `direct_click`
- `direct_press_key`
- `bypass_safety`

## TaskSpec Flow

1. User enters a natural language goal.
2. Provider proposes a JSON TaskSpec.
3. Sandbox validator checks schema, skill ids, safe tools, profile references, retry limits and dry-run graph simulation.
4. GUI displays the graph and risks.
5. User confirmation is required before execution.

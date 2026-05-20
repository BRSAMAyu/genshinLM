# Product E2E Report

- run_id: `561ee87e-94df-4dfb-93f6-40b181e9caf0`
- status: `FAILED`
- execution_mode: `safe-window`
- selected_profile: `default_1920x1080`
- selected_skill: `demo_product_skill`
- planner_provider: `mock`
- task_validation: `{'ok': False, 'errors': ['Safe-window mode requires selecting an authorized test window first.']}`
- release_all_called: `True`
- confirm_required: `False`
- error: `Safe-window mode requires selecting an authorized test window first.`

## Checklist Results
- [ ] Safe-window gate: Safe-window mode requires selecting an authorized test window first.

## Safety Events
- dry_run_default_verified
- f9_emergency_stop_enabled
- safe_window_rejected_or_confirmation_required

## Companion Summary
Safe-window execution is blocked until an authorized test window is selected and confirmed.
# Product E2E Report

- run_id: `27fbd559-cf2e-4f32-81e8-105f0986bd6e`
- status: `PASS`
- execution_mode: `dry-run`
- selected_profile: `default_1920x1080`
- selected_skill: `demo_product_skill`
- planner_provider: `mock`
- task_validation: `{'ok': True, 'errors': [], 'simulation': 'PASS'}`
- release_all_called: `True`
- confirm_required: `False`
- error: ``

## Checklist Results
- [x] FastAPI health: local service controller is available
- [x] Profile loaded: {'ok': True, 'profile_id': 'default_1920x1080', 'errors': []}
- [x] Model ready: backend=ultralytics tracker=botsort.yaml
- [x] Skill valid: {'ok': True, 'errors': []}
- [x] Planner ready: provider=mock validation=PASS
- [x] Safety ready: dry-run default, F9 enabled, safe-window required
- [x] Active profile exists: {'ok': True, 'profile_id': 'default_1920x1080', 'errors': []}
- [x] Skill validate OK: {'ok': True, 'errors': []}
- [x] Sandbox validation OK: {'ok': True, 'errors': [], 'simulation': 'PASS'}
- [x] Input backend safe: input_backend=console
- [x] Telemetry log path created: D:\Aurora\vision_agent_kernel_v0_5\logs\runs\27fbd559-cf2e-4f32-81e8-105f0986bd6e\product_e2e_trace.jsonl
- [x] Dry-run passed: SUCCESS
- [x] Report generated: D:\Aurora\vision_agent_kernel_v0_5\logs\runs\27fbd559-cf2e-4f32-81e8-105f0986bd6e\product_e2e_report.md

## Safety Events
- dry_run_default_verified
- f9_emergency_stop_enabled
- release_all_called

## Companion Summary
任务完成，已经整理好结果。
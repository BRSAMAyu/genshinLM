# Vision Agent MVP Demo Report

- run_dir: `D:\Aurora\vision_agent_kernel_v0_5\logs\runs\ee260cf2-bfff-4723-b1ef-248ab9f4fde5`
- records: 14
- release_all_called: unknown
- telemetry_drops: 0

## Runtime Health

- max_memory_mb: n/a
- memory_growth_mb: n/a
- avg_perception_fps: n/a
- avg_controller_fps: n/a
- max_telemetry_backlog: n/a

## State Transitions

- INIT -> LOAD_TASK: bootstrapped
- LOAD_TASK -> ENTER_TARGET_REGION: task_loaded
- ENTER_TARGET_REGION -> ACQUIRE_TARGET: target_region_entered
- ACQUIRE_TARGET -> TRACK_AND_APPROACH: target_acquired
- TRACK_AND_APPROACH -> EXECUTE_VISUAL_ACTION_BLOCK: in_range
- EXECUTE_VISUAL_ACTION_BLOCK -> VERIFY_SUCCESS: action_block_success
- VERIFY_SUCCESS -> COMPLETE: verified

## Tracking Stats

- no center error series found

## Progress / Frustration

- no frustration series found

## Interrupts

- none recorded

## Failures

- inspect trace files for skill_result failure_code entries.

# Showcase Report

- run_id: `4c15ecf9-34e2-4c62-bef3-48046fd6ebab`
- mode: `dry-run`
- final_outcome: `COMPLETE`
- input_backend: `console`
- release_all_called: `True`

## Combat Playbook
- playbook_id: `mock_combat_playbook`
- validation_ok: `True`
- nodes_executed: `burst_if_safe, dodge_if_danger, attack_if_safe, burst_if_safe`

## Skill And Reflex
- skill_success_rate: `1.0`
- dry_run_ok: `True`
- danger_events: `2`
- dodge_count: `1`
- dodge_success: `1`
- dodge_failure: `0`
- target_lost_count: `0`
- recovery_count: `0`

## Companion Summary
任务完成，已经整理好结果。

## Suggested Skill Patch
- Keep `danger_guard` before burst steps.
- Add `target_visible` checkpoint before resuming from a dodge.
- If consecutive dodge cooldown is hit, lower aggression or extend recovery window.
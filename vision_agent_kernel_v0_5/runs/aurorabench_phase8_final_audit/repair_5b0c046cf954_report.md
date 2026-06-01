# Benchmark Report: repair

- **Run ID**: 5b0c046cf954
- **Timestamp**: 2026-05-31T05:32:07.547026+00:00
- **Total Scenarios**: 4
- **Passed**: 4
- **Failed**: 0
- **Evidence Coverage Rate**: 100.00%

## Scenario Results

| Scenario | Passed | Evidence Count |
|----------|--------|---------------|
| target_lost_repair | PASS | 6 |
| visual_pollution_repair | PASS | 6 |
| timeout_recovery_repair | PASS | 6 |
| combined_failure_repair | PASS | 6 |

## Evidence Coverage

### target_lost_repair
- Coverage: 100.00%
- Evidence IDs: 83a816e9d4854d768fbf49e2bc95d542, patch_safe_combat_v1_c212e7ff, 2a247b82b439429096657da0f22ff065, 55da40a460a74fecb811f4b5f8f20118, 425356e7437047b9847db45d7faa146e, draft_cd5c7365-b694-4155-97da-19a78550143b

### visual_pollution_repair
- Coverage: 100.00%
- Evidence IDs: 5e2ef8e7e1b44c37ab67fffebdc11aa9, patch_safe_combat_v1_5ba1d2f2, d6141f5d98f64904b167cf99066a30d8, 889871f5026e4b129cde433feffdd2d1, 3f1db01c6faa4ba893ba2904bc70c3c9, draft_5c4a3289-923d-47a8-bf13-a23c69ba27cd

### timeout_recovery_repair
- Coverage: 100.00%
- Evidence IDs: d45c284c6b8f4b6d94ef2e78fb54071b, patch_combat_rotation_v2_59fc6d81, e517eac58c2c480db51c4972478740e9, 100d41c3dfa44d8b8fb47339204999fc, 11d34f20ffa94dfab6568bc12845b344, draft_b3ba9be6-ffd3-476f-a01d-231776f790fc

### combined_failure_repair
- Coverage: 100.00%
- Evidence IDs: 6d4fc94ba991466aa1e118b4dde7d0f9, patch_exploration_v1_69bbddaf, 118ede1c32db45ef9b7187ed1dcc30aa, 0fea8a9093d74b2b8280f33c96a00fb5, db18c89eaaa9455c8d784cdcd4b741a7, draft_834ed13d-1ee4-41d3-b73d-38f114c7f004

## Detailed Metrics

### target_lost_repair
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- skill_name: safe_combat_v1
- failure_code: TARGET_LOST
- patch_created: True
- patch_verified: True
- patch_approved: True
- benchmark_delta: True
- repair_sessions_created: 1
- skill_patch_drafts_created: 1

### visual_pollution_repair
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- skill_name: safe_combat_v1
- failure_code: VISUAL_POLLUTION
- patch_created: True
- patch_verified: True
- patch_approved: True
- benchmark_delta: True
- repair_sessions_created: 1
- skill_patch_drafts_created: 1

### timeout_recovery_repair
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- skill_name: combat_rotation_v2
- failure_code: COMBAT_TIMEOUT
- patch_created: True
- patch_verified: True
- patch_approved: True
- benchmark_delta: True
- repair_sessions_created: 1
- skill_patch_drafts_created: 1

### combined_failure_repair
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- skill_name: exploration_v1
- failure_code: NAVIGATION_FAILED
- patch_created: True
- patch_verified: True
- patch_approved: True
- benchmark_delta: True
- repair_sessions_created: 1
- skill_patch_drafts_created: 1

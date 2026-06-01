# Benchmark Report: reflex

- **Run ID**: 7bddcfc3ef36
- **Timestamp**: 2026-05-31T05:32:07.499783+00:00
- **Total Scenarios**: 6
- **Passed**: 6
- **Failed**: 0
- **Evidence Coverage Rate**: 63.89%

## Scenario Results

| Scenario | Passed | Evidence Count |
|----------|--------|---------------|
| ground_danger | PASS | 3 |
| projectile_danger | PASS | 3 |
| hp_drop_danger | PASS | 2 |
| target_occlusion | PASS | 4 |
| repeated_danger | PASS | 4 |
| false_positive | PASS | 0 |

## Evidence Coverage

### ground_danger
- Coverage: 75.00%
- Evidence IDs: evidence_preempt_preempt_1_frame_10, evidence_preempt_preempt_2_frame_20, evidence_resume_resume_preempt_2_frame_32

### projectile_danger
- Coverage: 75.00%
- Evidence IDs: evidence_preempt_preempt_1_frame_15, evidence_preempt_preempt_2_frame_25, evidence_resume_resume_preempt_2_frame_32

### hp_drop_danger
- Coverage: 100.00%
- Evidence IDs: evidence_preempt_preempt_1_frame_20, evidence_resume_resume_preempt_1_frame_32

### target_occlusion
- Coverage: 66.67%
- Evidence IDs: evidence_preempt_preempt_1_frame_10, evidence_preempt_preempt_2_frame_20, evidence_preempt_preempt_3_frame_30, evidence_resume_resume_preempt_3_frame_37

### repeated_danger
- Coverage: 66.67%
- Evidence IDs: evidence_preempt_preempt_1_frame_10, evidence_preempt_preempt_2_frame_30, evidence_preempt_preempt_3_frame_50, evidence_resume_resume_preempt_3_frame_72

### false_positive
- Coverage: 0.00%

## Detailed Metrics

### ground_danger
- frame_to_observation_ms: 0.005
- observation_to_interrupt_ms: 0.011
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 1.217
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 2
- final_task_success: True

**Report Details:**
- dodges: 2
- expected_dodges: 1
- resume_contracts: 1
- total_frames: 60

### projectile_danger
- frame_to_observation_ms: 0.002
- observation_to_interrupt_ms: 0.008
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.522
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 2
- final_task_success: True

**Report Details:**
- dodges: 2
- expected_dodges: 1
- resume_contracts: 1
- total_frames: 60

### hp_drop_danger
- frame_to_observation_ms: 0.004
- observation_to_interrupt_ms: 0.010
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.512
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 1
- final_task_success: True

**Report Details:**
- dodges: 1
- expected_dodges: 1
- resume_contracts: 1
- total_frames: 60

### target_occlusion
- frame_to_observation_ms: 0.002
- observation_to_interrupt_ms: 0.008
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 1.142
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 3
- final_task_success: True

**Report Details:**
- dodges: 3
- expected_dodges: 1
- resume_contracts: 1
- total_frames: 65

### repeated_danger
- frame_to_observation_ms: 0.004
- observation_to_interrupt_ms: 0.006
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 3.602
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 3
- final_task_success: True

**Report Details:**
- dodges: 3
- expected_dodges: 3
- resume_contracts: 1
- total_frames: 100

### false_positive
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- dodges: 0
- expected_dodges: 0
- resume_contracts: 0
- total_frames: 40

# Benchmark Report: boss_combat

- **Run ID**: b21b7dad7447
- **Timestamp**: 2026-05-31T05:32:07.475886+00:00
- **Total Scenarios**: 6
- **Passed**: 6
- **Failed**: 0
- **Evidence Coverage Rate**: 100.00%

## Scenario Results

| Scenario | Passed | Evidence Count |
|----------|--------|---------------|
| ground_aoe_clear | PASS | 5 |
| projectile_target_reacquire | PASS | 5 |
| team_no_healer_survives_conservative | PASS | 5 |
| emergency_hp_blocks_food_during_danger | PASS | 4 |
| food_profile_missing_safe_abort | PASS | 2 |
| long_fight_phase_shift | PASS | 10 |

## Evidence Coverage

### ground_aoe_clear
- Coverage: 100.00%
- Evidence IDs: frame:1, boss:aoe_boss:opening:1:boss, frame:2, frame:3, frame:4

### projectile_target_reacquire
- Coverage: 100.00%
- Evidence IDs: frame:1, boss:projectile_boss:ranged_loop:1:boss, frame:2, frame:3, frame:4

### team_no_healer_survives_conservative
- Coverage: 100.00%
- Evidence IDs: frame:1, boss:aoe_boss:opening:1:boss, frame:2, boss:aoe_boss:opening:2:boss, frame:3

### emergency_hp_blocks_food_during_danger
- Coverage: 100.00%
- Evidence IDs: frame:1, boss:phase_shift_boss:normal:1:boss, frame:2, frame:3

### food_profile_missing_safe_abort
- Coverage: 100.00%
- Evidence IDs: frame:1, boss:projectile_boss:ranged_loop:1:boss

### long_fight_phase_shift
- Coverage: 100.00%
- Evidence IDs: frame:1, boss:phase_shift_boss:normal:1:boss, frame:2, boss:phase_shift_boss:shielded:2:boss, frame:3, boss:phase_shift_boss:shielded:3:boss, frame:4, boss:phase_shift_boss:enrage:4:boss, frame:5, frame:6

## Detailed Metrics

### ground_aoe_clear
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.800
- max_consecutive_dodges: 0
- final_task_success: True
- boss_clear_rate: 1.000
- survival_rate: 1.000
- target_reacquire_success_rate: 1.000
- heal_success_rate: 1.000
- safe_abort_success_rate: 1.000

**Report Details:**
- group: boss_pattern
- boss_id: aoe_boss
- actions: ['dodge_reflex', 'hold_safe', 'hold_safe', 'finish']
- failure_signatures: []
- team_plan: team=shielder; boss=aoe_boss; conservative_level=0
- boss_clear_rate: 1.0
- survival_rate: 1.0
- heal_success_rate: 1.0

### projectile_target_reacquire
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.800
- max_consecutive_dodges: 0
- final_task_success: True
- boss_clear_rate: 1.000
- survival_rate: 1.000
- target_reacquire_success_rate: 1.000
- heal_success_rate: 1.000
- safe_abort_success_rate: 1.000

**Report Details:**
- group: boss_pattern
- boss_id: projectile_boss
- actions: ['lateral_dodge', 're_acquire_target', 'hold_safe', 'finish']
- failure_signatures: []
- team_plan: team=healer; boss=projectile_boss; conservative_level=1
- boss_clear_rate: 1.0
- survival_rate: 1.0
- heal_success_rate: 1.0

### team_no_healer_survives_conservative
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True
- boss_clear_rate: 1.000
- survival_rate: 1.000
- target_reacquire_success_rate: 1.000
- heal_success_rate: 1.000
- safe_abort_success_rate: 1.000

**Report Details:**
- group: team_diversity
- boss_id: aoe_boss
- actions: ['retreat_and_keep_distance', 'normal_attack', 'finish']
- failure_signatures: []
- team_plan: team=no_survival; boss=aoe_boss; conservative_level=2
- boss_clear_rate: 1.0
- survival_rate: 1.0
- heal_success_rate: 1.0

### emergency_hp_blocks_food_during_danger
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.800
- max_consecutive_dodges: 0
- final_task_success: True
- boss_clear_rate: 1.000
- survival_rate: 1.000
- target_reacquire_success_rate: 1.000
- heal_success_rate: 1.000
- safe_abort_success_rate: 1.000

**Report Details:**
- group: survival
- boss_id: phase_shift_boss
- actions: ['dodge_then_reacquire', 'hold_safe', 'finish']
- failure_signatures: []
- team_plan: team=no_survival; boss=phase_shift_boss; conservative_level=4
- boss_clear_rate: 1.0
- survival_rate: 1.0
- heal_success_rate: 1.0

### food_profile_missing_safe_abort
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: False
- boss_clear_rate: 0.000
- survival_rate: 1.000
- target_reacquire_success_rate: 1.000
- heal_success_rate: 1.000
- safe_abort_success_rate: 1.000

**Report Details:**
- group: survival
- boss_id: projectile_boss
- actions: ['release_all']
- failure_signatures: ['HEAL_PROFILE_NOT_READY']
- team_plan: team=no_survival; boss=projectile_boss; conservative_level=4
- boss_clear_rate: 0.0
- survival_rate: 1.0
- heal_success_rate: 1.0

### long_fight_phase_shift
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.800
- max_consecutive_dodges: 0
- final_task_success: True
- boss_clear_rate: 1.000
- survival_rate: 1.000
- target_reacquire_success_rate: 1.000
- heal_success_rate: 1.000
- safe_abort_success_rate: 1.000

**Report Details:**
- group: long_fight
- boss_id: phase_shift_boss
- actions: ['e_skill', 'normal_attack', 'wait_tactic', 'dodge_reflex', 'hold_safe', 'finish']
- failure_signatures: []
- team_plan: team=healer; boss=phase_shift_boss; conservative_level=1
- boss_clear_rate: 1.0
- survival_rate: 1.0
- heal_success_rate: 1.0

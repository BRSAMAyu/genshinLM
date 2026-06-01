# Benchmark Report: long_horizon

- **Run ID**: e45fea532147
- **Timestamp**: 2026-05-31T05:32:07.479680+00:00
- **Total Scenarios**: 4
- **Passed**: 4
- **Failed**: 0
- **Evidence Coverage Rate**: 91.67%

## Scenario Results

| Scenario | Passed | Evidence Count |
|----------|--------|---------------|
| full_chain_happy_path | PASS | 16 |
| combat_recovery_resume | PASS | 10 |
| double_interrupt_resume | PASS | 13 |
| collect_with_danger_interleave | PASS | 12 |

## Evidence Coverage

### full_chain_happy_path
- Coverage: 100.00%
- Evidence IDs: 7efbb7c8a06d44f086a531466e1a2225, 7074942302fb4d74a4ee412496c15e51, 6e5c713b7e574510b7490b4eb4d9fa69, 43e444c0c8624d7985eaf58412b1ff06, b36b93bf8b5f41bb9c2fd38deac99a31, 5cb4467e191c46178993ad1b29f3c5a3, 774f7a947b524e4f81c9f10995c2c627, 8773d1e0ba0f49538183de589d63c4e3, 60552cb6f93541dea2cdfedef9444115, 99285dcc55de402abbf758d6ce7cf86c
  ... and 6 more

### combat_recovery_resume
- Coverage: 66.67%
- Evidence IDs: c26af7f9a83f4ad2a4f9cd125b1fa69b, a9036243bf3847339a04aa964790ee69, 42d09eb6ff3f4a22ad90af7e50a17161, e12cee0c8d024e83baa222a3b7c83405, 92163e2260714cdbbf50fb68298749b2, 525bdf4a1eed4c43badf938b92b9ade5, e86ef2f4f1d041c89933a5ad78af4892, 687e26500c1e4cdfbf39cbca9faaeb89, 69aae13c480a43b9baa1baecf022277a, e6230d20801c416e827733b9316c2890

### double_interrupt_resume
- Coverage: 100.00%
- Evidence IDs: 92d451006029467fb79266fece3318fa, 1b2736e8a00543fc915f1d62491bb22f, 13754be7b4a64be7b5aa3f69ed33fe82, 66e0f5039d8a419698438aaa07d46b03, c12c8b218f17494ba8967f1a5db033c7, b2739f6b59974c6fb831067f19d5784b, c40c2a1949224422b940976877ee909a, eaefc17a08bf4e24908b8ece2dbea2bf, 9acf10d7b31e4a0ea979eed179173244, 09e0690517ac4697a7ec3b3c78153a3d
  ... and 3 more

### collect_with_danger_interleave
- Coverage: 100.00%
- Evidence IDs: 36e80c5ec93944a985cf73b5d3f4dd09, 25c0b81271444b319e281c00ce89a1b1, 5f6e5ee218dc4fc2975e68cc2316fc09, 22704644dc99491abcb3bcd612070ee1, 30143dff55e84cf19dcf5aa201496873, fbe22190e3174024a7aa2a120e7eb761, 997aed6d636e427fad80fbce3e7f05dc, 5a4fce43341847fa8e08e3c1825f8c09, ff7488e5330148b8bc9eb1bd4c9d096b, 789b504bdaf3404ebde026f6eb3cd461
  ... and 2 more

## Detailed Metrics

### full_chain_happy_path
- frame_to_observation_ms: 0.500
- observation_to_interrupt_ms: 0.188
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- phases_completed: ['knowledge_resolve', 'route_choose', 'enter_region', 'combat', 'danger_reflex', 'collect', 'forced_stop', 'hot_resume', 'final_verifier']
- nodes_visited: ['n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7', 'n8', 'n9']
- resume_skips: []
- interrupt_count: 1
- recovery_transitions: 1
- terminal_evidence_ok: True
- resume_skips_ok: True
- route_nodes: 9

### combat_recovery_resume
- frame_to_observation_ms: 0.500
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- phases_completed: ['combat', 'danger_reflex', 'hot_resume', 'final_verifier']
- nodes_visited: ['n1', 'n2', 'n3', 'n4', 'n5', 'n6']
- resume_skips: ['n1', 'n2']
- interrupt_count: 0
- recovery_transitions: 1
- terminal_evidence_ok: True
- resume_skips_ok: True
- route_nodes: 6

### double_interrupt_resume
- frame_to_observation_ms: 0.500
- observation_to_interrupt_ms: 0.097
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- phases_completed: ['knowledge_resolve', 'forced_stop', 'hot_resume', 'enter_region', 'forced_stop', 'hot_resume', 'final_verifier']
- nodes_visited: ['n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7']
- resume_skips: []
- interrupt_count: 2
- recovery_transitions: 2
- terminal_evidence_ok: True
- resume_skips_ok: True
- route_nodes: 7

### collect_with_danger_interleave
- frame_to_observation_ms: 0.500
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 1.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- phases_completed: ['route_choose', 'enter_region', 'collect', 'danger_reflex', 'hot_resume', 'collect', 'final_verifier']
- nodes_visited: ['n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7']
- resume_skips: []
- interrupt_count: 0
- recovery_transitions: 1
- terminal_evidence_ok: True
- resume_skips_ok: True
- route_nodes: 7

## Safety Summary

- **full_chain_happy_path** interrupts: 1
- **full_chain_happy_path** recoveries: 1
- **combat_recovery_resume** interrupts: 0
- **combat_recovery_resume** recoveries: 1
- **double_interrupt_resume** interrupts: 2
- **double_interrupt_resume** recoveries: 2
- **collect_with_danger_interleave** interrupts: 0
- **collect_with_danger_interleave** recoveries: 1

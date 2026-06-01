# Benchmark Report: ui_safety

- **Run ID**: 5e228e5ab911
- **Timestamp**: 2026-05-31T05:32:07.549025+00:00
- **Total Scenarios**: 5
- **Passed**: 5
- **Failed**: 0
- **Evidence Coverage Rate**: 100.00%

## Scenario Results

| Scenario | Passed | Evidence Count |
|----------|--------|---------------|
| safe_button_execute | PASS | 5 |
| destructive_action_blocked | PASS | 4 |
| low_confidence_requires_confirmation | PASS | 4 |
| mixed_safety_chain | PASS | 17 |
| confirmation_dialog_proceed | PASS | 4 |

## Evidence Coverage

### safe_button_execute
- Coverage: 100.00%
- Evidence IDs: 731c8f9ad7ca48d8a662607f52ad4ecf, c94fb751bbe5447db031783ec09208dd, 157e2d4fa8fe45a8a983d99a928f7265, b6520daad6cf4fe9820ce1c8d409a801, c022b03b771c4c94bfbef1b3822c156b

### destructive_action_blocked
- Coverage: 100.00%
- Evidence IDs: f68d18b6370747a1bb2794bad969f7f1, 063a0f4f37fb40fb89f3fa4e3754a97c, fbc1c514fcb54e15aa1f3b2a7d58bd58, d07288406e1c4bbd987d4223f8840368

### low_confidence_requires_confirmation
- Coverage: 100.00%
- Evidence IDs: 746fa7c873a243f49fec524fbf461def, 38b4bcd9a9034f6295746405a8d76c39, f506076ff4b94abbaf73fa303e37a7f3, d55a75a5b5de47839b75bfcf4c488bcc

### mixed_safety_chain
- Coverage: 100.00%
- Evidence IDs: f0c5a5d60eeb4915bf997c7cab332dd9, f4ecbf555ec64a90b63b5181209552d4, fe81551255ab451b8e0e2870f336bd66, e89e29a8af554dc4b902fef9df9443eb, bd2b545e4dc94c1ca48e68f341c1d538, 3eb4a65040bb4ecda6d01ee7c1af951b, ee7ab19232824104b8e4359da8e93345, 8faab31743cd4271b504a878cab1e0b9, a552ea3409584c369c15b0f5de28e06a, 2d9d365ac0424c4a96c3d61dd85eb884
  ... and 7 more

### confirmation_dialog_proceed
- Coverage: 100.00%
- Evidence IDs: adf9de84f92e47e3a9a0c98352933c88, 751a6da0bcac40b2a5cec8f2382dc6d0, c7417e63cd154d94adec532af30dd287, 59333c7f28c44755bcda34f1e91fb757

## Detailed Metrics

### safe_button_execute
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- safety_blocks: 0
- blocked_actions: []
- confirmation_required: 0
- confirm_elements: []
- executed_elements: ['btn_start']
- element_results: [{'element_id': 'btn_start', 'classification': 'execute', 'label': 'Start', 'confidence': 0.95}]
- blocked_ok: True
- confirm_ok: True
- execute_ok: True
- verifier_results: True

### destructive_action_blocked
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- safety_blocks: 1
- blocked_actions: ['btn_delete']
- confirmation_required: 0
- confirm_elements: []
- executed_elements: []
- element_results: [{'element_id': 'btn_delete', 'classification': 'blocked', 'label': 'Delete All', 'confidence': 0.92}]
- blocked_ok: True
- confirm_ok: True
- execute_ok: True
- verifier_results: True

### low_confidence_requires_confirmation
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- safety_blocks: 0
- blocked_actions: []
- confirmation_required: 1
- confirm_elements: ['btn_confirm']
- executed_elements: []
- element_results: [{'element_id': 'btn_confirm', 'classification': 'confirm', 'label': 'Confirm Purchase', 'confidence': 0.45}]
- blocked_ok: True
- confirm_ok: True
- execute_ok: True
- verifier_results: True

### mixed_safety_chain
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- safety_blocks: 1
- blocked_actions: ['btn_sell']
- confirmation_required: 2
- confirm_elements: ['sld_volume', 'btn_ok']
- executed_elements: ['btn_navigate']
- element_results: [{'element_id': 'btn_navigate', 'classification': 'execute', 'label': 'Navigate', 'confidence': 0.9}, {'element_id': 'btn_sell', 'classification': 'blocked', 'label': 'Sell Item', 'confidence': 0.88}, {'element_id': 'sld_volume', 'classification': 'confirm', 'label': 'Volume', 'confidence': 0.35}, {'element_id': 'btn_ok', 'classification': 'confirm', 'label': 'OK', 'confidence': 0.85}]
- blocked_ok: True
- confirm_ok: True
- execute_ok: True
- verifier_results: True

### confirmation_dialog_proceed
- frame_to_observation_ms: 0.000
- observation_to_interrupt_ms: 0.000
- interrupt_to_lease_ms: 0.000
- danger_clear_time_ms: 0.000
- danger_false_clear_rate: 0.000
- resume_success_rate: 0.000
- max_consecutive_dodges: 0
- final_task_success: True

**Report Details:**
- safety_blocks: 0
- blocked_actions: []
- confirmation_required: 1
- confirm_elements: ['dlg_confirm_exit']
- executed_elements: []
- element_results: [{'element_id': 'dlg_confirm_exit', 'classification': 'confirm', 'label': 'Confirm Exit', 'confidence': 0.9}]
- blocked_ok: True
- confirm_ok: True
- execute_ok: True
- verifier_results: True

## Safety Summary

- **safe_button_execute** safety blocks: 0
- **safe_button_execute** blocked: []
- **safe_button_execute** verifier: True
- **destructive_action_blocked** safety blocks: 1
- **destructive_action_blocked** blocked: ['btn_delete']
- **destructive_action_blocked** verifier: True
- **low_confidence_requires_confirmation** safety blocks: 0
- **low_confidence_requires_confirmation** blocked: []
- **low_confidence_requires_confirmation** verifier: True
- **mixed_safety_chain** safety blocks: 1
- **mixed_safety_chain** blocked: ['btn_sell']
- **mixed_safety_chain** verifier: True
- **confirmation_dialog_proceed** safety blocks: 0
- **confirmation_dialog_proceed** blocked: []
- **confirmation_dialog_proceed** verifier: True

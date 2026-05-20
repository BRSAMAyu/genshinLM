# Combat Intelligence

Combat intelligence is split into high-level planning and local reflex handling.

## Playbook Graph

`combat/playbook_schema.py` defines playbook nodes, edges, guards, priority, fallback, retry, and success/failure conditions. The mock strategist generates a dry-run playbook through `/combat/playbook`.

Example nodes:

- `maintain_lock`
- `target_visible_checkpoint`
- `attack_if_safe`
- `burst_if_safe`
- `heal_if_low_hp`
- `dodge_if_danger`
- `fallback_basic_loop`
- `verify_complete`

`combat/playbook_runtime.py` validates the graph, performs dry-run traversal, and can evaluate one behavior-tree tick from `CombatContext` plus `danger_score`. High danger interrupts into `dodge_if_danger`; low HP routes to `heal_if_low_hp`; safe target lock routes to attack or burst nodes. Every generated playbook must include retry bounds, a fallback node, and a reflex dodge node.

## Reflex Evasion

`combat/danger_detector.py` computes `DangerScore` from:

- `generic_warning_score` from `generic_warning_area`
- `projectile_threat_score` from `projectile_approaching`
- `distance_closing_score` from `target_bbox_fast_expand` and `enemy_facing_player`
- `hp_drop_score` from `hp_drop_signal`
- `scripted_testbed_score` from sandbox danger events
- `combat_context_priority` from local tactical context

When the score crosses the high threshold, the service emits a P1 `DODGE_REFLEX` interrupt and asks `DodgePolicy` for a short dry-run dodge intent. Dodge cooldown and `max_consecutive_dodges` prevent repeated infinite evasion. When cooldown blocks a dodge, the runtime keeps or resumes from the current checkpoint and may fall back to `fallback_basic_loop`.

## Testbed Signals

`testbed/pseudo3d_scene.py --combat-demo` renders enemy attack warning arcs, projectile motion, danger-zone overlay, HP drift, dodge feedback, target stun/recovery state, and an overlay with `danger_score`, `hp`, and `dodge_cooldown`.

Manual keys:

- `G`: trigger a scripted combat danger event.
- `D`: simulate a dodge feedback event.
- Existing chaos keys (`Space`, `T`, `O`, `M`) remain available for target loss and ambiguity testing.

## Showcase

Run the final dry-run showcase:

```powershell
python scripts/run_showcase_demo.py --mode dry-run --seconds 30
```

The script writes `logs/runs/<run_id>/showcase_trace.jsonl` and `logs/runs/<run_id>/showcase_report.md` with playbook nodes executed, danger events, dodge count, recovery count, companion summary, and suggested skill patches.

## Safety

Combat modules do not perform raw input. They generate validated playbooks, interrupts, and dry-run dodge intents. Real execution remains gated by safe-window input and user confirmation.

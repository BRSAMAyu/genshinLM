# Capsule Specification

> **Purpose**: Define the YAML + Python plugin capsule system for game-specific adaptations.
> **Status**: Implemented (capsules/ directory, capsule_protocol.py)
> **Parent**: SPARKLE_AGENT_KERNEL_DESIGN.md

---

## Overview

A **Capsule** is a self-contained game adapter that provides skills, detectors, verifiers,
UI anchors, and keymaps without polluting the core kernel. The kernel is game-agnostic;
capsules are game-specific.

```
Kernel (game-agnostic)
  └─ Capsule (game-specific)
       ├─ capsule.yaml — declarative manifest
       ├─ entrypoint.py — Python lifecycle hooks
       ├─ skills/ — skill implementations
       └─ resources/ — YAML data, images, templates
```

## CapsuleManifest Schema

```yaml
capsule_id: genshin          # Unique identifier
version: "0.5.0"             # Semantic version
display_name: "Genshin Impact"
description: "Genshin Impact game adapter"
runtime_package: capsules.genshin
entrypoint: GenshinCapsule   # Python class name

capabilities:                 # What this capsule provides
  - screen_classification
  - combat_control
  - ui_navigation

frame_processors:             # Perception pipeline post-processors
  - GenshinScreenClassifier

slots:                        # StateBus slots to register
  combat_signal:
    type: CombatSignal
    default: null

skills:                       # Skill declarations
  - skill_id: character_level_up
    kind: skill
    capabilities_provided: [ui_operation]
    risk_level: medium
    verifiers: [level_change_verifier]
    ui_anchors: [character_menu, level_button]
    planner_tags: [progression, ui]

verifiers:                    # Verifier implementations
  - verifier_id: level_change_verifier
    type: ocr_delta

detectors:                    # Visual detector implementations
  - detector_id: minimap_detector
    type: hsv_roi

keymaps:                      # Game key mapping
  open_character_menu: C
  open_party: L
  interact: F
  open_map: M

resources:                    # Static data files
  - resource_id: world_graph
    kind: yaml
    path: data/world_graph.yaml
```

## Capsule Python Protocol

```python
class Capsule(Protocol):
    capsule_id: str

    def install(self, context: CapsuleContext) -> None: ...
    def activate(self) -> None: ...
    def deactivate(self) -> None: ...
    @property
    def is_active(self) -> bool: ...
    def uninstall(self, context: CapsuleContext) -> None: ...
```

`CapsuleContext` provides: `state_bus`, `pipeline`, `orchestrator`, `mode_arbiter`.

## CapsuleSkillSpec

Each skill declares:
- `skill_id`: unique within capsule
- `kind`: "skill" | "flow" | "reflex"
- `capabilities_provided`: what this skill can do
- `capabilities_required`: what must be available to run
- `risk_level`: "low" | "medium" | "high" | "critical"
- `failure_modes`: list of known failure scenarios
- `recovery_policy`: how to recover from failures
- `verifiers`: list of verifier IDs for post-action verification
- `ui_anchors`: UI elements this skill interacts with

## Patch Flow

Permanent changes to capsule YAML go through `CapsulePatchProposal`:

```
draft → schema_validated → diff_reviewed → replay_verified → user_confirmed → committed
```

Each stage is immutable (frozen dataclass). Committing without user confirmation is rejected.

Existing capsules: `genshin/`, `hsr/`, `desktop_ui/`, `demo_arpg/`.

---

*Source: `capsules/capsule_protocol.py`, `runtime/claim_runtime.py::CapsulePatchProposal`*

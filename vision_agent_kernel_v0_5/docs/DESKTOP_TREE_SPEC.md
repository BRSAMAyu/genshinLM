# DesktopTree Specification

> **Purpose**: Template anchoring, ROI OCR, geometric clustering for UI tree verification.
> **Status**: Implemented (interaction/desktop_tree.py)
> **Parent**: SPARKLE_AGENT_KERNEL_DESIGN.md

---

## Overview

**DesktopTree** is the structured representation of on-screen UI elements. It provides
a hierarchical tree of UI nodes with bounding boxes, roles, text, and state — analogous
to an accessibility tree but built from visual perception (VLM/OCR/H).

```
Frame
  → ObservationGraph (from perception pipeline)
  → DesktopTreeBuilder.build()
  → DesktopTree (hierarchical node tree)
  → used by: ScreenStateClaimBuilder, UIFlowSkillAdapter, Verifiers
```

## Core Types

### DesktopNode

```python
@dataclass(frozen=True, slots=True)
class DesktopNode:
    node_id: str
    role: str          # window|panel|list|button|text|icon|selected_item|modal|unknown
    bbox: NormalizedRect
    confidence: float
    source: str        # "vlm" | "ocr" | "classifier" | "template" | "heuristic"
    text: str
    state: str         # "enabled" | "disabled" | "selected" | "hidden"
    children: tuple[DesktopNode, ...]
    evidence_ref: str
    payload: dict
```

### DesktopTree

```python
@dataclass(frozen=True, slots=True)
class DesktopTree:
    tree_id: str
    root_id: str
    screen_state: str    # matched from genshin_screen_classifier
    viewport: tuple[int, int]
    nodes: dict[str, DesktopNode]

    def by_role(self, role: str) -> list[DesktopNode]: ...
    def find_text(self, query: str) -> list[DesktopNode]: ...
```

### DesktopTreeBuilder

```python
class DesktopTreeBuilder:
    def build(self, observation_graph: ObservationGraph) -> DesktopTree: ...
```

Constructs the tree from the perception pipeline's `ObservationGraph` output.

## Role Classification

| Role | Description | Detection Method |
|------|-------------|------------------|
| `window` | Top-level window frame | VLM |
| `panel` | Sub-section of a window | VLM + geometry |
| `list` | Scrollable list container | VLM + layout |
| `button` | Clickable action element | Template + VLM |
| `text` | Static or dynamic text | OCR |
| `icon` | Visual icon/symbol | Template matching |
| `selected_item` | Currently selected element | State tracking |
| `modal` | Modal dialog/popup | VLM + overlay detection |
| `unknown` | Unrecognized element | Fallback |

## Template Anchoring

Template anchoring uses pre-defined ROI coordinates for known UI elements:

```yaml
# Reference coordinates at 1920x1080
character_menu:
  tab_bar: (0.90, 0.28) - (0.95, 0.75)
  level_display: (1500, 150) - (1700, 220)
  confirm_button: (0.65, 0.85)
  action_button: (0.85, 0.85)
```

These are game-specific and live in capsule YAML, NOT in the kernel.

## UI Tree Verification

The DesktopTree is used by verifiers to confirm UI state changes:

1. **Pre-action tree**: Snapshot before action execution.
2. **Action**: Click/type/navigation.
3. **Post-action tree**: Snapshot after stabilization window.
4. **Delta detection**: Compare pre vs post trees for expected changes.

## Geometric Clustering

When VLM/OCR returns unstructured element detections, geometric clustering groups
nearby elements into logical containers:

- Bounding box overlap → same panel
- Vertical alignment → same list
- Horizontal alignment → tab bar
- Center clustering → modal content

## Scope

DesktopTree handles **2D UI** only. 3D world navigation requires `WorldStateGraph`.

---

*Source: `interaction/desktop_tree.py`, `planning/screen_state_claim_builder.py`*

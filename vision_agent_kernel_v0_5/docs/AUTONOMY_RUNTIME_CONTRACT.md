# AUTONOMY_RUNTIME_CONTRACT

> **Purpose**: Freeze field definitions, state machines, and invariants for all
> runtime contracts in the Sparkle Project. This is the authoritative reference —
> no subsequent phase may redefine these contracts without updating this document.
>
> **Version**: v0.5.1
> **Generated**: 2026-05-31
> **Supersedes**: ad-hoc dataclass definitions scattered across `core/types.py`,
> `planning/screen_state_claim.py`, `execution/semantic_action.py`,
> `runtime/claim_runtime.py`, `perception/pipeline.py`

---

## TABLE OF CONTENTS

1. [Core Data Types](#1-core-data-types)
2. [State Machines](#2-state-machines)
3. [StateBus Slot Mappings](#3-statebus-slot-mappings)
4. [Invariants](#4-invariants)
5. [Execution Contract Flow](#5-execution-contract-flow)
6. [Verification Contract](#6-verification-contract)
7. [Checkpoint Contract](#7-checkpoint-contract)
8. [VLM Usage Contract](#8-vlm-usage-contract)

---

## 1. CORE DATA TYPES

All types are declared with `@dataclass(slots=True)` (mutable fields) or
`@dataclass(frozen=True, slots=True)` (immutable). No other declaration style
is allowed for runtime contracts.

---

### 1.1 Observation

High-frequency (~30–60 fps) game state snapshot. Written by `PerceptionPipeline`
to `StateBus.latest_observation`. Consumed by control loops.

```python
@dataclass(slots=True)
class Observation:
    frame_id: int                          # monotonically increasing
    t_capture: float                       # time.perf_counter() at capture
    t_processed: float                     # time.perf_counter() after processing
    latency_ms: float                      # t_processed - t_capture in ms
    viewport_size: tuple[int, int]        # (width, height)

    target_track: TargetTrack | None       # MUST NOT be None after Phase 1
    obstacle_field: ObstacleField | None   # MUST NOT be None after Phase 1
    ui_state: UIStateEstimate | None       # MUST NOT be None after Phase 1
    visual_triggers: dict[str, bool]       # always non-empty dict
    os_focus: FocusState

    stale: bool = False                    # True if latency_ms > stale_threshold_ms
    extensions: dict[str, object] = field(default_factory=dict)
```

**TargetTrack** (must be populated after PerceptionFusionRuntime Phase 1):

```python
@dataclass(slots=True)
class TargetTrack:
    track_id: str
    class_id: str           # "enemy", "npc", "chest", "waypoint", etc.
    state: str              # "visible", "missing", "dead"
    bbox_xyxy: tuple[float, float, float, float] | None
    smoothed_center_px: tuple[float, float] | None
    velocity_px_s: tuple[float, float]
    confidence: float       # 0.0–1.0
    identity_confidence: float
    missing_duration_ms: float
    bearing_deg: float | None
    pitch_deg: float | None
    estimated_range: float | None
    last_seen_frame_id: int
    appearance_signature: JsonDict | None = None
```

**ObstacleField** (must be populated after Phase 1):

```python
@dataclass(slots=True)
class ObstacleField:
    frame_id: int
    timestamp: float
    sectors: dict[str, float]          # direction → distance (0 = blocked)
    confidence: float
    source: str                          # "hsv", "depth", "vlm"
```

**UIStateEstimate** (must be populated after Phase 1):

```python
@dataclass(slots=True)
class UIStateEstimate:
    frame_id: int
    timestamp: float
    state: str                          # ScreenStateKind value
    confidence: float                   # 0.0–1.0
    payload: JsonDict = field(default_factory=dict)
```

**FocusState**:

```python
@dataclass(slots=True)
class FocusState:
    focused: bool
    window_title: str | None = None
    process_name: str | None = None
```

---

### 1.2 ScreenStateClaim

Medium-frequency (~2–5 Hz) semantic game state. Written by `ScreenStateClaimBuilder`
to `StateBus.screen_claim`. Consumed by planning and decision layers.

```python
ScreenStateKind = Literal[
    "overworld", "combat", "turn_based_combat", "dialog", "menu",
    "map", "loading", "inventory", "shop", "quest_log", "reward_screen",
    "boss_fight", "cutscene", "death_screen", "character_select",
    "adventure_rank_up", "notification", "domain_entrance",
    "cooking", "forging", "unknown",
]

ClaimSource = Literal["vlm", "ocr", "classifier", "template", "hybrid", "unknown"]

@dataclass(frozen=True, slots=True)
class UIElementClaim:
    element_id: str
    role: str           # "button", "menu_item", "dialog_option", "teleport_point", etc.
    text: str
    bbox_norm: tuple[float, float, float, float]  # 0.0–1.0 normalized
    confidence: float
    source: ClaimSource
    clickable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class PlayerStatusClaim:
    health_pct: float | None = None
    stamina_pct: float | None = None
    skill_points: int | None = None
    position: str = "unknown"

@dataclass(frozen=True, slots=True)
class ScreenStateClaim:
    game_id: str
    screen_state: ScreenStateKind
    confidence: float                   # 0.0–1.0
    source: ClaimSource
    ui_elements: tuple[UIElementClaim, ...] = ()
    player_status: PlayerStatusClaim = field(default_factory=PlayerStatusClaim)
    visible_objects: tuple[dict[str, str], ...] = ()
    interaction_prompt: str = ""
    scene_description: str = ""
    frame_id: int = 0
    timestamp: float = 0.0
    raw_vlm_text: str = ""
    raw_ocr_texts: tuple[str, ...] = ()

    # Derived views — MUST be implemented
    def actionable_elements(self) -> list[UIElementClaim]: ...
    def text_elements(self) -> dict[str, str]: ...
    def find_element(self, role: str) -> UIElementClaim | None: ...
```

---

### 1.3 SemanticAction

Unified action primitive. All execution flows MUST emit `SemanticAction` instances.
No business logic may emit raw key codes or pixel coordinates.

```python
ActionKind = Literal["ui", "navigation", "combat", "system"]
RiskLevel = Literal["low", "medium", "high", "human_confirm"]

@dataclass(frozen=True, slots=True)
class SemanticAction:
    action_id: str         # unique per-session, format: "{skill}_{seq}_{intent}"
    kind: ActionKind
    intent: str            # "teleport", "click_anchor", "combat_encounter", etc.
    target: str = ""       # semantic target, e.g. "mon:windrise", "npc:amber"
    parameters: dict[str, Any] = field(default_factory=dict)
    requires_physical_input: bool = False
```

---

### 1.4 ActionContract

Contracts bind a `SemanticAction` to preconditions, execution policy, safety policy,
expected state delta, and verifier contract.

```python
@dataclass(frozen=True, slots=True)
class ActionContract:
    action_id: str
    semantic_action: SemanticAction
    preconditions: list[str] = field(default_factory=list)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    safety_policy: dict[str, Any] = field(default_factory=dict)
    expected_state_delta: dict[str, Any] = field(default_factory=dict)
    verifier_contract: dict[str, Any] = field(default_factory=dict)
    fallback_policy: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 1000
    risk_level: RiskLevel = "medium"
    evidence_links: list[str] = field(default_factory=list)

    @property
    def is_physical(self) -> bool:
        return self.semantic_action.requires_physical_input
```

**Safety policy required fields** for physical actions:
- `require_focus: bool = True`
- `input_lease_required: bool = True`
- `max_lease_ms: int > 0`

---

### 1.5 PhysicalReceipt

Proof-of-execution record. Every physical action MUST return a `PhysicalReceipt`.
A `bool` return value alone is NOT acceptable after Phase 2.

```python
class ReceiptStatus(Literal):
    PENDING = "pending"
    SUBMITTED = "submitted"
    LEASE_ACCEPTED = "lease_accepted"
    FOCUS_OK = "focus_ok"
    EXECUTED = "executed"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"

@dataclass(frozen=True, slots=True)
class PhysicalReceipt:
    action_id: str
    status: ReceiptStatus
    submitted_at: float
    lease_accepted: bool = False
    focus_ok: bool = False
    duration_ms: float = 0.0
    post_state_claim_id: str = ""        # links to ScreenStateClaim after action
    verifier_result: VerifierResult | None = None
    reason: str = ""
    failed_step: str = ""                # "lease_request", "focus_check", "backend_call", "verification"
    backend_type: str = ""               # "console", "safe_window", "direct_input", "background"

    @property
    def is_verified(self) -> bool:
        return self.status == "verified" and self.verifier_result is not None and self.verifier_result.ok

    @property
    def success(self) -> bool:
        return self.status in ("executed", "verified") and self.lease_accepted and self.focus_ok
```

---

### 1.6 StateDeltaClaim

Post-action state change assertion. Consumed by ClaimGraph for belief maintenance.

```python
ClaimStatus = Literal[
    "asserted", "tentative", "verified", "locked", "audited",
    "uncertain", "disputed", "suspect", "demoted", "reverified", "rejected", "expired", "error",
]
RiskLevel = Literal["low", "medium", "high", "critical"]

@dataclass(frozen=True, slots=True)
class StateDeltaClaim:
    claim_id: str
    mission_id: str
    node_id: str
    skill_id: str
    claim_type: str                    # e.g. "navigation_arrival", "combat_victory"
    claimed_delta: dict[str, Any]
    status: ClaimStatus = "asserted"
    risk_level: RiskLevel = "medium"
    confidence: float = 0.0
    confidence_factors: ConfidenceFactors | None = None
    evidence_refs: list[str] = field(default_factory=list)
    signals: list[SignalEvidence] = field(default_factory=list)
    input_claims: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    inferred_depends_on: list[str] = field(default_factory=list)
    stabilization_window_ms: int = 1000
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Stabilization defaults** (`ClaimType → ms`):
| claim_type | stabilization_ms |
|---|---|
| ui_screen_transition | 800 |
| dialogue_advance | 500 |
| inventory_delta | 1200 |
| collection_pickup | 900 |
| teleport_loaded | 1500 |
| navigation_arrival | 700 |
| combat_target_killed | 1200 |
| boss_phase_changed | 1800 |
| danger_cleared | 200 |
| generic_unknown | 1000 |

---

### 1.7 NavigationPlan

Output of `MapNavigationRuntime.select_destination()`.

```python
@dataclass(frozen=True, slots=True)
class AnchorScreenLocation:
    anchor_id: str
    screen_xy: tuple[float, float]       # normalized 0.0–1.0
    confidence: float                    # 0.0–1.0
    locked: bool = False                 # True = not yet unlocked by player
    cooldown_until: float = 0.0          # unix time, 0 = no cooldown

@dataclass(frozen=True, slots=True)
class NavigationLeg:
    method: Literal["teleport", "walk", "swim"]
    waypoint_id: str = ""
    target_xy: tuple[float, float] = (0.0, 0.0)
    expected_duration_sec: float = 0.0

@dataclass(frozen=True, slots=True)
class NavigationPlan:
    plan_id: str
    objective: str                        # e.g. "mon:windrise", "npc:amber"
    legs: tuple[NavigationLeg, ...] = ()
    fallback_allowed: bool = True
    timeout_sec: float = 120.0
    failed_legs: tuple[str, ...] = ()
    arrived: bool = False
    arrived_leg_index: int = -1
```

---

### 1.8 CombatSignal

Combat decision input. Consumed by `CombatRuntime`.

```python
@dataclass(slots=True)
class CombatSignal:
    enemy_visible: bool = False
    enemy_count: int = 0
    enemy_hp_ratio: float = 1.0         # 0.0–1.0, -1 = unknown
    enemy_aura: str = ""                # "pyro", "electro", "cryo", "hydro", "geo", "anemo", "dendro", "none"
    enemy_shield_element: str = ""      # element of shield, "" = no shield
    enemy_shield_hp_pct: float = 0.0   # 0–100
    enemy_class: str = ""

    player_hp_ratio: float = 1.0
    player_stamina_ratio: float = 1.0
    player_skill_e_ready: bool = True
    player_burst_q_ready: bool = False
    player_energy_pct: float = 0.0

    danger_score: float = 0.0           # 0.0–1.0
    aoe_incoming: bool = False
    aoe_eta_sec: float = 99.0

    boss_phase: int = 1
    boss_enraged: bool = False
    boss_mechanic_active: str = ""      # "dps_burn", "teleport", "summon", ""

    incoming_hitstun: bool = False
    combo_broken: bool = False
    frame_id: int = 0
    timestamp: float = 0.0
```

**CombatAction** (output of CombatPolicy):

```python
@dataclass(frozen=True, slots=True)
class CombatAction:
    action: Literal["attack", "skill_e", "burst_q", "switch", "dodge", "heal", "shield", "retreat", "wait"]
    target_slot: int = 0                 # 1–4 for switch
    reason: str = ""
    priority: int = 0                   # lower = higher priority
    parameters: dict[str, Any] = field(default_factory=dict)
```

---

### 1.9 DialogChoiceClaim

Dialog branch selection output.

```python
ClaimSource = Literal["vlm", "ocr", "classifier", "template", "hybrid", "unknown"]

@dataclass(frozen=True, slots=True)
class DialogChoiceClaim:
    claim_id: str
    frame_id: int
    timestamp: float
    choices: tuple[DialogChoice, ...] = ()
    selected_index: int = -1             # -1 = none selected
    confidence: float = 0.0
    source: ClaimSource = "unknown"

@dataclass(frozen=True, slots=True)
class DialogChoice:
    index: int
    text: str
    bbox_norm: tuple[float, float, float, float]
    clickable: bool = True
    reason: str = ""                    # why this was/wasn't selected
```

---

## 2. STATE MACHINES

### 2.1 PhysicalReceipt State Machine

```
PENDING → SUBMITTED → LEASE_ACCEPTED → FOCUS_OK → EXECUTED → VERIFIED
                         ↓
                    (lease rejected)
                         ↓
                      EXPIRED

Any state → FAILED (on unrecoverable error)
```

Transitions:
- `PENDING → SUBMITTED`: InputWorker accepted the lease request
- `SUBMITTED → LEASE_ACCEPTED`: lease granted by InputLeaseStore
- `SUBMITTED → EXPIRED`: lease rejected (timeout, focus lost, priority conflict)
- `LEASE_ACCEPTED → FOCUS_OK`: backend confirms target window focused
- `LEASE_ACCEPTED → FAILED`: focus lost before execution
- `FOCUS_OK → EXECUTED`: backend confirms physical input submitted
- `EXECUTED → VERIFIED`: post-action ClaimGraph confirmed state delta
- `EXECUTED → FAILED`: verification failed, action did not achieve expected delta
- `VERIFIED → FAILED`: post-hoc ClaimGraph detected discrepancy

### 2.2 ClaimStatus State Machine

```
asserted → verified → locked → audited
    ↓         ↓
tentative → reverified
    ↓
uncertain → disputed → demoted
    ↓                   ↓
  rejected           rejected
    ↓
  expired
```

### 2.3 Perception Quality State Machine

```
INIT → STALE_DETECTED → RECOVERING → HEALTHY
                ↓
            DEGRADED → RECOVERING
```

- `STALE_DETECTED`: latency_ms > threshold for > 3 consecutive frames
- `RECOVERING`: last 5 frames all within threshold
- `DEGRADED`: > 50% frames stale over 30-frame window
- `HEALTHY`: < 10% stale over 30-frame window

---

## 3. STATEBUS SLOT MAPPINGS

Every slot listed here MUST exist in `StateBus.__post_init__()`.

| Slot Name | Type | Producer | Consumers |
|---|---|---|---|
| `latest_observation` | `LatestSlot[Observation]` | PerceptionPipeline | ControllerLoop, CombatRuntime, NavigationRuntime |
| `observation_ring` | `RingBuffer[Observation]` (300 frames) | PerceptionPipeline | ClaimGraphWorker, analytics |
| `screen_claim` | `LatestSlot[ScreenStateClaim]` | ScreenStateClaimBuilder | AutonomousTaskBrain, Planner |
| `affordances` | `LatestSlot[list[ActionAffordance]]` | AffordanceDeriver | Planner, SkillApplicabilityGate |
| `frame_quality` | `LatestSlot[FrameQuality]` | PerceptionFusionRuntime | all decision consumers |
| `navigation_signal` | `LatestSlot[NavigationSignal]` | NavigationRuntime | AutonomousTaskBrain |
| `combat_signal` | `LatestSlot[CombatSignal]` | CombatRuntime | AutonomousTaskBrain |
| `mission_graph` | `LatestSlot[MissionGraph]` | Planner | MainlineRunner |
| `claim_graph_state` | `LatestSlot[ClaimGraphState]` | ClaimGraphWorker | all decision consumers |
| `checkpoint_state` | `LatestSlot[CheckpointState]` | CheckpointStore | MainlineRunner, recovery |
| `navigation_plan` | `LatestSlot[NavigationPlan]` | MapNavigationRuntime | QuestMarkerFollower |
| `action_request` | `PriorityEventQueue[ActionRequest]` | Planner | InputWorker |
| `interrupt_queue` | `PriorityEventQueue[Interrupt]` | all sources | ControllerLoop, InputWorker |
| `shutdown_flag` | `threading.Event` | HumanOverride, Sentinel | all loops |

**FrameQuality** definition:

```python
@dataclass(frozen=True, slots=True)
class FrameQuality:
    frame_id: int
    latency_ms: float
    target_track_populated: bool
    obstacle_field_populated: bool
    ui_state_populated: bool
    visual_triggers_count: int
    staleness_rate_30f: float           # 0.0–1.0, fraction stale over last 30 frames
    quality_score: float = 0.0         # 0.0–1.0 composite
    timestamp: float = 0.0
```

---

## 4. INVARIANTS

These invariants MUST hold at all times. Tests MUST cover violations.

### 4.1 Observation Invariants

1. `frame_id` MUST be monotonically increasing across all frames in a session.
2. `t_processed >= t_capture` (monotonic clock only).
3. `latency_ms == (t_processed - t_capture) * 1000`.
4. `stale == True` iff `latency_ms > stale_threshold_ms`.
5. After Phase 1: `target_track is not None` within 100 frames of session start.
6. After Phase 1: `ui_state is not None` within 100 frames of session start.
7. `visual_triggers` is NEVER an empty dict (at minimum contains `static_visual_triggers`).

### 4.2 ScreenStateClaim Invariants

1. `confidence` is in range `[0.0, 1.0]`.
2. `ui_elements` tuple is NEVER `None` (empty tuple allowed).
3. Each `UIElementClaim.bbox_norm` values are in `[0.0, 1.0]`.
4. `screen_state` is always a valid `ScreenStateKind` value.
5. `post_state_claim` (`PhysicalReceipt.post_state_claim_id`) MUST NOT reference the same
   claim as `pre_state_claim`.

### 4.3 PhysicalReceipt Invariants

1. `submitted_at` uses `time.perf_counter()`, never `time.time()`.
2. `status` transitions follow the state machine in §2.1.
3. `duration_ms >= 0`.
4. `success == True` implies `lease_accepted == True` and `focus_ok == True`.
5. `is_verified == True` implies `success == True`.
6. `verifier_result is not None` iff `status in (VERIFIED, FAILED)`.
7. No `PhysicalReceipt` with `status == "pending"` may remain in the system for > 30s.

### 4.4 ActionContract Invariants

1. `timeout_ms > 0` always.
2. Physical actions (`requires_physical_input == True`) MUST have:
   - `safety_policy["require_focus"] == True`
   - `safety_policy["input_lease_required"] == True`
   - `safety_policy["max_lease_ms"] > 0`
3. `verifier_contract["verifier_id"]` is non-empty in strict mode.
4. High-risk actions MUST have a non-empty `fallback_policy`.

### 4.5 NavigationPlan Invariants

1. `legs` is NEVER empty.
2. `arrived == True` implies `arrived_leg_index >= 0`.
3. `arrived == False` and `arrived_leg_index >= 0` is INVALID.
4. `failed_legs` indices are strictly less than `arrived_leg_index`.
5. `timeout_sec > 0`.

---

## 5. EXECUTION CONTRACT FLOW

Every physical action follows this exact contract chain:

```
SemanticAction
    ↓ ActionContractValidator
ActionContract (validated)
    ↓ InputLeaseStore.request_lease()
PhysicalReceipt(status=PENDING)
    ↓ lease accepted → status=SUBMITTED → LEASE_ACCEPTED
    ↓ lease rejected → status=EXPIRED → return with reason
PhysicalReceipt(status=LEASE_ACCEPTED)
    ↓ InputWorker._apply_lease() → backend.execute()
    ↓ backend → status=SUBMITTED or EXPIRED
PhysicalReceipt(status=EXECUTED)
    ↓ post-action ScreenStateClaimBuilder → post_claim
    ↓ verifier_result = Verifier.verify(post_claim, contract)
    ↓ verifier_result.ok → status=VERIFIED
    ↓ !verifier_result.ok → status=FAILED
PhysicalReceipt(status=VERIFIED)
    ↓ ClaimGraphWorker.process_delta(post_claim)
```

**Prohibited patterns** (enforced by linter/contract tests):
1. Calling `backend.key_*()` without an `InputLease` in scope.
2. Returning `bool` from executor methods — MUST return `PhysicalReceipt`.
3. Bypassing `ActionContractValidator` for physical actions.
4. Asserting `success == True` without `verifier_result.ok == True`.
5. Using raw `(x, y)` coordinates in any `SemanticAction.parameters`.

---

## 6. VERIFICATION CONTRACT

Every `SemanticAction` MUST have a corresponding `Verifier` registered.

```python
class Verifier(Protocol):
    verifier_id: str
    def verify(
        self,
        context: VerifierContext,
        contract: ActionContract,
    ) -> VerifierResult: ...
```

**VerifierContext** always contains:
- `state: dict[str, Any]` — pre and post state snapshots
- `observation: Observation | None` — post-action frame
- `frame: np.ndarray | None` — raw post-action frame
- `roi_frames: dict[str, np.ndarray]` — cropped ROIs
- `ocr_text: str` — post-action OCR
- `target_track: TargetTrack | None`

**Required verifier behaviors**:
- MUST NOT return `ok=True` based solely on executor return value.
- MUST use `Observation` or post-action `ScreenStateClaim` as primary evidence.
- MUST set `re_verify_recommended=True` if `false_negative_likelihood > 0.2`.
- MUST include `alternative_signals` if primary signal confidence < 0.8.

---

## 7. CHECKPOINT CONTRACT

All long-running tasks (mainline chapter, daily deep, boss fight) MUST checkpoint.

```python
@dataclass(frozen=True, slots=True)
class CheckpointState:
    session_id: str
    mission_id: str
    node_id: str                    # last successfully completed node
    phase: str                       # "planning", "executing", "paused", "recovering"
    completed_nodes: tuple[str, ...] = ()
    failed_nodes: tuple[str, ...] = ()
    pending_nodes: tuple[str, ...] = ()
    claim_graph_snapshot: dict[str, Any] = field(default_factory=dict)
    belief_graph_version: int = 0
    last_claim_id: str = ""
    created_at: float = field(default_factory=time.time)
    checksum: str = ""               # sha256 of critical fields
```

**Checkpoint invariants**:
1. `completed_nodes` and `pending_nodes` are mutually exclusive.
2. `failed_nodes` is a strict subset of `completed_nodes ∪ pending_nodes`.
3. Resume MUST NOT replay `completed_nodes`.
4. Resume MUST restore claim graph from `claim_graph_snapshot`.
5. `checksum` MUST cover: `session_id`, `mission_id`, `node_id`, `completed_nodes`.

---

## 8. VLM USAGE CONTRACT

VLM is a **semantic completer and uncertainty arbiter**, not a per-step action oracle.

**Permitted VLM uses**:
1. Scene description when multiple detector signals disagree.
2. Dialog choice selection when `DialogBranchAnalyzer` confidence < 0.7.
3. Unknown screen state classification when classifier confidence < 0.6.
4. Verification arbitration when two verifiers disagree.
5. Claim adjudication when `ClaimStatus` is `uncertain` or `disputed`.

**Prohibited VLM uses**:
1. Direct pixel-coordinate output for clicking.
2. Every-frame state classification (use classifier/OCR instead).
3. Action selection when detector confidence >= 0.8.
4. Generating new SemanticAction without detector input.

**Rate limits**:
- VLM calls per mission: ≤ 20 (tracked in `VLMUsageTracker`)
- VLM fallback threshold: detector confidence < 0.6
- VLM arbitration threshold: verifier disagreement with `false_negative_likelihood > 0.3`

---

## CHANGE LOG

| Date | Change |
|------|--------|
| 2026-05-31 | Initial contract freeze |
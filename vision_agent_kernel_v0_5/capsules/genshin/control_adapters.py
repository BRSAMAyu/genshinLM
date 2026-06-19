"""Live-perception adapters for the game-agnostic reference controllers.

The three reference controllers
(:class:`~combat.reactive_combat_controller.ReactiveCombatController`,
:class:`~interaction.interaction_controller.InteractionController`,
:class:`~puzzle.puzzle_controller.PuzzleController`) are fully tested but are only
ever driven by ``harness/sim/*`` today. This module is the missing glue: it
translates what *live* perception actually produces (a
:class:`~core.types.Observation` plus a screen-state string from
:class:`~perception.genshin_screen_classifier.GenshinScreenClassifier`) into the
controllers' input ``View`` dataclasses, and translates the controllers' output
``Action`` dataclasses into the executor's input unit
(:class:`agent_kernel.types.SemanticAction`) using the capsule keymap.

Design rules honoured here:

* Additive only — no controller, loop, or factory is edited.
* Honest about impedance mismatch. Live perception today does NOT expose
  per-character HP/energy/skill-cooldown, enemy aura, enemy weaknesses, dialogue
  text/choices via OCR, or a metric puzzle target. Every such gap is marked with
  a ``TODO(perception)`` and given a *safe* default — one that makes the
  controller act conservatively (normal attack / advance dialogue / re-propose)
  rather than dangerously (mistimed dodge / wrong dialogue branch / blind move).
  The full residual list is in this module's docstring tail and in the task
  return.
* Monotonic clock only (this module performs no timing of its own).

Residual missing-perception fields (block full live combat / interaction /
puzzle until a provider supplies them) — see ``COMBAT_RESIDUALS`` etc. below.
"""
from __future__ import annotations

from typing import Any

from combat.reactive_combat_controller import (
    CombatAction,
    CombatCharView,
    CombatView,
)
from interaction.interaction_controller import InteractionAction, InteractionView
from puzzle.puzzle_controller import PuzzleAction, PuzzleView

from agent_kernel.types import SemanticAction

# ---------------------------------------------------------------------------
# Keymap
# ---------------------------------------------------------------------------
# The genshin capsule declares its keymap inline under ``keymaps:`` in
# ``capsules/genshin/capsule.yaml`` (loaded into ``CapsuleManifest.keymaps`` as a
# flat ``dict[str, str]``). We mirror it here as a default so the adapters are
# usable standalone in tests, but every translator accepts a ``keymap`` arg so
# the integrator can pass the live manifest's dict instead.
DEFAULT_GENSHIN_KEYMAP: dict[str, str] = {
    "interact": "F",
    "normal_attack": "LMB",
    "elemental_skill": "E",
    "elemental_burst": "Q",
    "sprint": "Shift",
    "jump": "Space",
}

# Map a controller intent to the *logical* keymap entry it needs. Switching
# characters and dodging have no entry in the genshin keymap above (party slots
# are 1-4; dodge is a Shift tap), so they are handled explicitly below.
_COMBAT_KIND_TO_KEYMAP: dict[str, str] = {
    "attack": "normal_attack",
    "skill": "elemental_skill",
    "burst": "elemental_burst",
    "heal": "elemental_skill",  # a healer's heal is its elemental skill press
}

# Logical party-slot keys (Genshin: characters 1-4 on the number row). Not in the
# capsule keymap because the keymap models verbs, not slots. The integrator may
# override via the ``party_slot_keys`` arg.
DEFAULT_PARTY_SLOT_KEYS: tuple[str, ...] = ("1", "2", "3", "4")

# Genshin dodge is a Shift tap (sprint key, tapped not held). Reuse the sprint
# key from the keymap; exposed as a constant so the residual is explicit.
_DODGE_KEYMAP = "sprint"


# ===========================================================================
# Perception -> View builders
# ===========================================================================

# Screen-state strings (from GenshinScreenClassifier) that mean "in combat".
_COMBAT_SCREEN_STATES = frozenset({"combat"})
# Screen-state strings that mean "an interaction surface is on screen".
_DIALOG_SCREEN_STATES = frozenset({"dialog", "cutscene"})
_REWARD_SCREEN_STATES = frozenset({"notification"})


def _ext(observation: Any, key: str, default: Any) -> Any:
    """Read an optional hint from ``Observation.extensions`` with a default.

    ``extensions`` is the only place live perception can stash richer combat /
    interaction signals today, so adapters prefer it when present and otherwise
    fall back to the safe default. Never raises.
    """
    try:
        ext = getattr(observation, "extensions", None) or {}
        return ext.get(key, default)
    except Exception:  # pragma: no cover - defensive, extensions is a plain dict
        return default


def build_combat_view(
    observation: Any,
    screen_state: str,
    *,
    chars: tuple[CombatCharView, ...] | None = None,
    active_index: int = 0,
) -> CombatView:
    """Build a :class:`CombatView` from live perception.

    Live perception (``Observation`` + screen-state) gives us a single
    ``TargetTrack`` (the locked enemy) and a screen-state string. It does NOT
    give us per-character HP/energy/skill state, the enemy's elemental aura, or
    the enemy's weaknesses. So:

    * ``enemy_hp_ratio`` — TODO(perception): needs an enemy-HP-bar reader. With
      no reader we cannot know the enemy is near-dead, so we default to ``1.0``
      (full). That is the *safe* default: it only ever permits a burst (the
      controller refuses to burst below ``burst_min_enemy_hp``), never blocks a
      needed action.
    * ``incoming_attack`` — TODO(perception): needs an enemy-telegraph detector.
      Defaulting to ``True`` would make the agent dodge constantly (and ``can_dodge``
      gates it on a real cooldown we also lack), so we default to ``False``: the
      agent will not perform a *mistimed* dodge. A real reflex-evasion path
      (``combat/reflex_evasion.py``) already handles danger via P1 interrupts, so
      this view never needs to invent telegraphs.
    * ``can_dodge`` — no live dodge-cooldown source; default ``True`` is inert
      because ``incoming_attack`` defaults ``False``.
    * ``enemy_aura`` / ``enemy_weaknesses`` — TODO(perception): needs aura
      detection / monster-DB lookup keyed on the tracked enemy's ``class_id``.
      Empty defaults degrade rotation to "first ready other", per the
      controller's own documented fall-through. Both are read from
      ``observation.extensions`` when a capsule provider populates them.
    * ``chars`` — TODO(perception): needs a party-state reader (HP bars, energy
      orbs, skill-cooldown icons). With none, the caller MUST pass ``chars``
      explicitly (e.g. from a capsule combat provider / team profile). If absent
      we synthesize a single conservative DPS char with skills/burst *not* ready,
      so the controller falls through to a plain ``attack`` — never a phantom
      burst/heal/switch.
    """
    track = getattr(observation, "target_track", None)

    enemy_present = (
        screen_state in _COMBAT_SCREEN_STATES
        or (track is not None and getattr(track, "class_id", "") not in ("", "player"))
    )

    # enemy_hp_ratio: TODO(perception): needs <enemy_hp_bar_ratio>. Safe default 1.0.
    enemy_hp_ratio = float(_ext(observation, "enemy_hp_ratio", 1.0 if enemy_present else 0.0))
    # enemy_aura: TODO(perception): needs <enemy_elemental_aura>. Safe default "".
    enemy_aura = str(_ext(observation, "enemy_aura", ""))
    # enemy_weaknesses: TODO(perception): needs <enemy_weaknesses from monster DB>.
    weaknesses_raw = _ext(observation, "enemy_weaknesses", ())
    enemy_weaknesses = tuple(str(w) for w in weaknesses_raw)
    # incoming_attack: TODO(perception): needs <enemy_telegraph_detector>. Safe
    # default False (no mistimed dodge; reflex_evasion handles real danger).
    incoming_attack = bool(_ext(observation, "incoming_attack", False))
    # can_dodge: TODO(perception): needs <dodge_cooldown>. Inert default True.
    can_dodge = bool(_ext(observation, "can_dodge", True))

    if chars is None:
        # chars: TODO(perception): needs <party_state: per-char hp/energy/skill/burst>.
        # Conservative single-DPS placeholder: nothing ready => controller attacks.
        chars = (
            CombatCharView(
                index=0,
                name="active",
                element="physical",
                hp_ratio=1.0,
                energy_ratio=0.0,
                skill_ready=False,
                burst_ready=False,
                role="dps",
            ),
        )
        active_index = 0

    if not 0 <= active_index < len(chars):
        active_index = 0

    return CombatView(
        active_index=active_index,
        chars=chars,
        enemy_hp_ratio=enemy_hp_ratio,
        enemy_aura=enemy_aura,
        incoming_attack=incoming_attack,
        can_dodge=can_dodge,
        enemy_weaknesses=enemy_weaknesses,
    )


def build_interaction_view(
    observation: Any,
    screen_state: str,
    *,
    objective_hint: str = "",
) -> InteractionView:
    """Build an :class:`InteractionView` from live perception.

    The screen-state string maps cleanly onto the interaction screen vocabulary,
    but the *contents* of a dialogue (choices text, prompt text, reward-ready
    flag) come from OCR / UI parsing that the bare ``Observation`` does not carry
    inline. Where a richer signal exists it is read from ``observation.extensions``
    (a capsule dialog provider can populate ``dialogue_choices`` / ``prompt_text``);
    otherwise we degrade safely.

    * ``screen`` — derived from the classifier state. ``dialog``/``cutscene`` ->
      ``"dialogue"``, ``notification`` -> ``"reward"``, anything with a live
      prompt -> ``"prompt"``, else ``"none"``.
    * ``choices`` — TODO(perception): needs <dialogue choice OCR>. Default ``()``
      so the controller advances the dialogue rather than picking a blind branch
      (a wrong branch can dead-end a quest — picking blind is the dangerous move).
    * ``prompt`` — TODO(perception): needs <interact-prompt OCR>. Default "".
    * ``reward_ready`` — derived from screen-state ``notification`` + an optional
      extension flag.
    """
    raw = (screen_state or "").lower()
    choices_raw = _ext(observation, "dialogue_choices", ())
    choices = tuple(str(c) for c in choices_raw)
    prompt = str(_ext(observation, "prompt_text", ""))
    reward_ready = bool(_ext(observation, "reward_ready", raw in _REWARD_SCREEN_STATES))

    if raw in _DIALOG_SCREEN_STATES:
        screen = "dialogue"
        dialogue_active = True
    elif reward_ready or raw in _REWARD_SCREEN_STATES:
        screen = "reward"
        dialogue_active = False
    elif prompt:
        screen = "prompt"
        dialogue_active = False
    elif choices:
        screen = "choice"
        dialogue_active = False
    else:
        screen = "none"
        dialogue_active = False

    return InteractionView(
        screen=screen,
        dialogue_active=dialogue_active,
        choices=choices,
        prompt=prompt,
        reward_ready=reward_ready,
        objective_hint=objective_hint,
    )


def build_puzzle_view(
    observation: Any,
    screen_state: str,
    *,
    current: tuple[float, float] | None = None,
    target: tuple[float, float] | None = None,
    error: tuple[float, float] | None = None,
    tolerance: float = 2.0,
    attempts_this_phase: int = 0,
    stage: str = "explore",
) -> PuzzleView:
    """Build a :class:`PuzzleView` from live perception.

    Puzzles are the deepest impedance mismatch: the controller closes a *metric*
    error loop in some puzzle coordinate frame (a movable piece, a click point, a
    camera alignment), but a bare ``Observation`` has no notion of a puzzle target
    or error vector. Those come from the PROPOSE step (VLM names the target) plus
    a local detector (REFINE sharpens it) — neither is part of perception's
    standard output.

    So the metric fields are caller-supplied and default to the *explore* regime:

    * ``target`` — TODO(perception): needs <VLM-proposed puzzle target>. Default
      ``None`` => controller emits ``propose`` (ask the VLM), the correct and safe
      first move. We opportunistically seed ``current``/``target`` from a tracked
      object's screen-pixel centre (``observation.target_track``) when the caller
      passes none, but this is only a coarse pixel proxy — see residuals.
    * ``error`` — TODO(perception): needs <refined target-vs-current error>.
      Default ``None`` => controller emits ``refine`` (sharpen the measurement),
      never a blind ``act``.
    * ``current`` — from the tracked object's smoothed pixel centre when present,
      else ``(0.0, 0.0)``.
    """
    track = getattr(observation, "target_track", None)
    if current is None:
        center = getattr(track, "smoothed_center_px", None) if track is not None else None
        current = (float(center[0]), float(center[1])) if center else (0.0, 0.0)

    return PuzzleView(
        stage=stage,
        current=current,
        target=target,
        tolerance=tolerance,
        error=error,
        attempts_this_phase=attempts_this_phase,
    )


# ===========================================================================
# Action -> SemanticAction translators
# ===========================================================================


def _resolve_key(keymap: dict[str, str], logical: str, fallback: str) -> str:
    return keymap.get(logical, fallback)


def combat_action_to_semantic(
    action: CombatAction,
    keymap: dict[str, str] | None = None,
    *,
    party_slot_keys: tuple[str, ...] = DEFAULT_PARTY_SLOT_KEYS,
    action_id: str = "combat_action",
) -> SemanticAction:
    """Translate a :class:`CombatAction` to a physical-input ``SemanticAction``.

    Maps the controller's intent to a real key from the capsule keymap. ``switch``
    resolves to a party-slot key (1-4); ``dodge`` to the sprint/dodge key. The
    LLM-stays-strategic rule holds: the controller picks *which* intent, the
    keymap supplies the key, and nothing here invents pixel motion.
    """
    km = keymap or DEFAULT_GENSHIN_KEYMAP
    kind = action.kind
    params: dict[str, str] = {"controller_kind": kind, "reason": action.reason}

    if kind == "switch":
        idx = action.switch_to
        if 0 <= idx < len(party_slot_keys):
            key = party_slot_keys[idx]
        else:
            key = party_slot_keys[0]
        params["switch_to"] = str(idx)
        key_intent = "switch_character"
    elif kind == "dodge":
        key = _resolve_key(km, _DODGE_KEYMAP, "Shift")
        key_intent = "dodge"
    else:
        logical = _COMBAT_KIND_TO_KEYMAP.get(kind, "normal_attack")
        key = _resolve_key(km, logical, "LMB")
        key_intent = kind

    params["key"] = key
    return SemanticAction(
        action_id=action_id,
        kind="combat",
        intent=key_intent,
        target="locked_enemy",
        parameters=tuple(sorted(params.items())),
        requires_physical_input=True,
    )


def interaction_action_to_semantic(
    action: InteractionAction,
    keymap: dict[str, str] | None = None,
    *,
    action_id: str = "interaction_action",
) -> SemanticAction:
    """Translate an :class:`InteractionAction` to a ``SemanticAction``.

    ``advance``/``confirm``/``interact``/``claim`` all press the interact key.
    ``choose`` is a click on the choice's UI zone — but live perception does not
    yet give us choice click-zones, so we emit a ``ui``/``select_dialog_choice``
    action carrying the index for the executor's UI layer to resolve, and DO NOT
    fabricate raw x/y (which the contract validator would reject anyway).
    ``idle`` maps to a non-physical system no-op.
    """
    km = keymap or DEFAULT_GENSHIN_KEYMAP
    kind = action.kind
    interact_key = _resolve_key(km, "interact", "F")

    if kind == "idle":
        return SemanticAction(
            action_id=action_id,
            kind="system",
            intent="idle",
            target="",
            parameters=(("controller_kind", "idle"), ("reason", action.reason)),
            requires_physical_input=False,
        )

    if kind == "choose":
        # choice click-zone: TODO(perception): needs <choice UI zone OCR>. We pass
        # the semantic index, not raw pixels, for the UI layer to ground.
        return SemanticAction(
            action_id=action_id,
            kind="ui",
            intent="select_dialog_choice",
            target=f"choice_{action.choice_index}",
            parameters=tuple(sorted({
                "controller_kind": "choose",
                "choice_index": str(action.choice_index),
                "reason": action.reason,
            }.items())),
            requires_physical_input=True,
        )

    # advance / confirm / interact / claim -> press interact key.
    return SemanticAction(
        action_id=action_id,
        kind="ui",
        intent="advance_interaction",
        target="dialog",
        parameters=tuple(sorted({
            "controller_kind": kind,
            "key": interact_key,
            "reason": action.reason,
        }.items())),
        requires_physical_input=True,
    )


def puzzle_action_to_semantic(
    action: PuzzleAction,
    keymap: dict[str, str] | None = None,
    *,
    action_id: str = "puzzle_action",
) -> SemanticAction:
    """Translate a :class:`PuzzleAction` to a ``SemanticAction``.

    ``propose``/``refine``/``verify`` are *cognitive* steps with no physical
    input — they route to the VLM / detector / re-observation, so they are emitted
    as ``system`` actions (no lease). ``act`` carries a metric ``delta`` that the
    capsule's puzzle handler must map into game motion (cursor move, camera nudge,
    piece drag) — we pass the delta through as parameters rather than guessing the
    physical mapping here. ``escalate``/``done`` are terminal system signals.
    """
    kind = action.kind
    if kind == "act":
        dx, dy = action.delta
        return SemanticAction(
            action_id=action_id,
            kind="ui",
            intent="puzzle_step",
            target="puzzle_target",
            parameters=tuple(sorted({
                "controller_kind": "act",
                "delta_x": repr(float(dx)),
                "delta_y": repr(float(dy)),
                "reason": action.reason,
            }.items())),
            # delta->physical mapping: TODO(perception): needs <puzzle motion
            # actuator> (cursor/camera/drag). Marked physical so the executor
            # gates it behind a lease once a handler grounds the delta.
            requires_physical_input=True,
        )

    # propose / refine / verify / escalate / done -> cognitive, no physical input.
    return SemanticAction(
        action_id=action_id,
        kind="system",
        intent=f"puzzle_{kind}",
        target="puzzle",
        parameters=tuple(sorted({"controller_kind": kind, "reason": action.reason}.items())),
        requires_physical_input=False,
    )


# ===========================================================================
# Residuals — missing-perception fields that block full live operation.
# ===========================================================================
# These lists are the honest accounting of what perception must add before the
# controllers can run end-to-end on live frames (not just sim). They are exported
# so the integrator / a perception-roadmap task can consume them programmatically.

COMBAT_RESIDUALS: tuple[str, ...] = (
    "enemy_hp_ratio (enemy HP-bar reader)",
    "incoming_attack (enemy telegraph / wind-up detector)",
    "can_dodge (player dodge-cooldown tracker)",
    "enemy_aura (enemy elemental-aura detector)",
    "enemy_weaknesses (monster-DB lookup keyed on tracked class_id)",
    "chars (party state: per-character hp/energy/skill_ready/burst_ready)",
)

INTERACTION_RESIDUALS: tuple[str, ...] = (
    "choices (dialogue choice-text OCR)",
    "prompt (interact-prompt-text OCR)",
    "reward_ready (reward-screen detector beyond 'notification')",
    "choice click-zones (UI grounding for select_dialog_choice)",
)

PUZZLE_RESIDUALS: tuple[str, ...] = (
    "target (VLM-proposed puzzle target in a metric frame)",
    "error (refined current-vs-target error vector)",
    "delta->physical mapping (puzzle motion actuator: cursor/camera/drag)",
    "tolerance (per-puzzle convergence tolerance in the target's frame)",
)

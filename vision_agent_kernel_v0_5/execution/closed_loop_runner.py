"""ClosedLoopRunner — minimal end-to-end proof of the autonomy closed loop.

Chains:
    Companion text → TaskSpec → SkillRecipe lookup → DesktopTree/ScreenClaim
    → ActionContract → ExecutionRuntime (InputLease dry-run) → post-action
    ObservationClaim → StateDeltaClaim verification → RuntimeOverride /
    CapsulePatchProposal → replay/audit log.

This is the thinnest orchestrator that proves the architecture works. It does
NOT implement game-specific logic — that lives in Capsules and SkillRecipes.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from execution.execution_runtime import ExecutionRuntime, PhysicalReceipt
from execution.semantic_action import ActionContract, SemanticAction
from planning.screen_state_claim_builder import ScreenStateClaimBuilder
from runtime.claim_runtime import (
    CapsulePatchProposal,
    ClaimGraph,
    ObservationClaim,
    RuntimeOverrideClaim,
    StateDeltaClaim,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class TaskSpecResolver(Protocol):
    """Resolve companion text to a TaskSpec."""
    def resolve(self, text: str) -> TaskSpecResult: ...


class SkillRecipeLookup(Protocol):
    """Look up a SkillRecipe from a capsule for a given capability."""
    def lookup(self, capability: str) -> SkillRecipe | None: ...


class ScreenClaimProvider(Protocol):
    """Build a ScreenClaim from the current frame."""
    def build_claim(self) -> ScreenClaimResult: ...


class OverridePolicyValidator(Protocol):
    """Validate a RuntimeOverrideClaim before application."""
    def validate(self, override: RuntimeOverrideClaim) -> RuntimeOverrideClaim: ...


class VerificationProvider(Protocol):
    """Verify post-action state via VLM/OCR or other observation-based check."""
    def verify(self, task: TaskSpecResult, screen: ScreenClaimResult) -> VerificationResult: ...


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verified: bool
    confidence: float = 0.0
    method: str = "none"  # "vlm" | "ocr" | "receipt" | "self_assert" | "none"
    details: str = ""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TaskSpecResult:
    task_id: str
    capability: str          # e.g. "character_level_up"
    target: str = ""         # e.g. "hu_tao"
    parameters: dict[str, Any] = field(default_factory=dict)
    success_criteria: str = ""
    confidence: float = 0.8


@dataclass(frozen=True, slots=True)
class SkillRecipe:
    skill_id: str
    capsule_id: str
    steps: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    verifier_contract: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"


@dataclass(frozen=True, slots=True)
class ScreenClaimResult:
    claim_id: str
    screen_state: str
    ui_elements: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    raw_frame: Any = None


@dataclass(frozen=True, slots=True)
class LoopStepResult:
    step: str
    success: bool
    duration_ms: float
    details: str | TaskSpecResult | SkillRecipe | ScreenClaimResult = ""
    receipt: PhysicalReceipt | None = None
    claim: StateDeltaClaim | None = None
    override: RuntimeOverrideClaim | None = None
    patch: CapsulePatchProposal | None = None


@dataclass(frozen=True, slots=True)
class ClosedLoopResult:
    loop_id: str
    task_id: str
    success: bool
    total_duration_ms: float
    steps: tuple[LoopStepResult, ...] = ()
    final_state: str = "unknown"


# ---------------------------------------------------------------------------
# Default implementations (for testing / dry-run)
# ---------------------------------------------------------------------------

class SimpleTaskSpecResolver:
    """Basic resolver that extracts capability from text via keyword matching.

    Keywords are matched longest-first so that compound phrases like "天赋升级"
    prefer the more specific "天赋" match over the generic "升级".
    """

    _KEYWORDS: dict[str, str] = {
        # Genshin Impact — ordered longest-first for disambiguation
        "天赋升级": "talent_upgrade",
        "圣遗物强化": "artifact_enhance",
        "圣遗物装备": "artifact_equip",
        "武器强化": "weapon_enhance",
        "武器精炼": "weapon_refine",
        "武器装备": "weapon_equip",
        "祈愿十连": "wish_pull",
        "圣遗物": "artifact_equip",
        "天赋": "talent_upgrade",
        "升级": "character_level_up",
        "突破": "character_ascend",
        "强化": "weapon_enhance",
        "精炼": "weapon_refine",
        "武器": "weapon_equip",
        "祈愿": "wish_pull",
        # English
        "talent upgrade": "talent_upgrade",
        "weapon enhance": "weapon_enhance",
        "weapon refine": "weapon_refine",
        "artifact enhance": "artifact_enhance",
        "artifact equip": "artifact_equip",
        "wish pull": "wish_pull",
        "wish ten": "wish_pull",
        "level up": "character_level_up",
        "ascend": "character_ascend",
        "talent": "talent_upgrade",
        "weapon": "weapon_equip",
        "artifact": "artifact_equip",
        "wish": "wish_pull",
        "enhance": "weapon_enhance",
        "refine": "weapon_refine",
        # Genshin combat — generic
        "世界boss": "combat_world_boss",
        "周本": "combat_weekly",
        "深渊法师": "combat_abyss_mage",
        "丘丘人": "combat_basic",
        "精英怪": "combat_shield_break",
        "打怪": "combat_basic",
        "杀boss": "combat_boss",
        "战斗": "combat_basic",
        "world boss": "combat_world_boss",
        "weekly boss": "combat_weekly",
        "abyss mage": "combat_abyss_mage",
        "boss fight": "combat_boss",
        "fight": "combat_basic",
        # Genshin combat — boss-specific (#4-9)
        "风魔龙": "combat_boss_dvalin",
        "特瓦林": "combat_boss_dvalin",
        "dvalin": "combat_boss_dvalin",
        "stormterror": "combat_boss_dvalin",
        "公子": "combat_boss_childe",
        "达达利亚": "combat_boss_childe",
        "childe": "combat_boss_childe",
        "tartaglia": "combat_boss_childe",
        "女士": "combat_boss_signora",
        "罗莎琳": "combat_boss_signora",
        "signora": "combat_boss_signora",
        "雷电将军": "combat_boss_raiden",
        "将军": "combat_boss_raiden",
        "raiden shogun": "combat_boss_raiden",
        "正机之神": "combat_boss_shouki",
        "散兵boss": "combat_boss_shouki",
        "scaramouche boss": "combat_boss_shouki",
        "巨鲸": "combat_boss_narwhal",
        "吞噬一切的巨鲸": "combat_boss_narwhal",
        "narwhal": "combat_boss_narwhal",
        # Genshin combat — environment (#12-13)
        "龙脊雪山": "combat_env_dragonspine",
        "雪山战斗": "combat_env_dragonspine",
        "极寒": "combat_env_dragonspine",
        "dragonspine": "combat_env_dragonspine",
        "稻妻雷暴": "combat_env_inazuma",
        "雷暴战斗": "combat_env_inazuma",
        "inazuma storm": "combat_env_inazuma",
        # Genshin combat — abyss (#10-11)
        "深境螺旋": "combat_abyss",
        "螺旋": "combat_abyss",
        "深渊": "combat_abyss",
        "spiral abyss": "combat_abyss",
        "abyss floor": "combat_abyss",
        # Genshin combat — multi-wave (#16)
        "多波次": "combat_multi_wave",
        "防守战": "combat_multi_wave",
        "multi wave": "combat_multi_wave",
        "defense": "combat_multi_wave",
        # Genshin combat — rotations (#14-15)
        "周本循环": "combat_weekly_rotation",
        "周本轮换": "combat_weekly_rotation",
        "weekly rotation": "combat_weekly_rotation",
        "世界boss循环": "combat_world_farming",
        "boss farming": "combat_world_farming",
        "世界boss扫荡": "combat_world_farming",
        # Genshin exploration
        "传送锚点": "explore_waypoint",
        "传送锚点激活": "explore_waypoint",
        "七天神像": "explore_statue",
        "神像激活": "explore_statue",
        "宝箱": "explore_chest",
        "普通宝箱": "explore_chest",
        "精致宝箱": "explore_chest",
        "珍贵宝箱": "explore_chest",
        "华丽宝箱": "explore_chest",
        "开宝箱": "explore_chest",
        "神瞳": "explore_oculus",
        "风神瞳": "explore_oculus",
        "岩神瞳": "explore_oculus",
        "雷神瞳": "explore_oculus",
        "草神瞳": "explore_oculus",
        "水神瞳": "explore_oculus",
        "冰神瞳": "explore_oculus",
        "火神瞳": "explore_oculus",
        "元素方碑": "explore_puzzle",
        "火炬解谜": "explore_puzzle",
        "压力板": "explore_puzzle",
        "限时挑战": "explore_timed",
        "死域": "explore_withering",
        "水下探索": "explore_underwater",
        "枫丹水下": "explore_underwater",
        "解谜": "explore_puzzle",
        # English exploration
        "activate waypoint": "explore_waypoint",
        "waypoint activation": "explore_waypoint",
        "open chest": "explore_chest",
        "chest opening": "explore_chest",
        "collect oculus": "explore_oculus",
        "oculus collection": "explore_oculus",
        "elemental monument": "explore_puzzle",
        "torch puzzle": "explore_puzzle",
        "pressure plate": "explore_puzzle",
        "timed challenge": "explore_timed",
        "withering zone": "explore_withering",
        "underwater": "explore_underwater",
        "fontaine underwater": "explore_underwater",
        "activate statue": "explore_statue",
        "puzzle": "explore_puzzle",
        # Genshin quest
        "推进对话": "quest_dialog",
        "对话选择": "quest_dialog_select",
        "跳过过场": "quest_skip_cutscene",
        "任务日志": "quest_read_log",
        "每日委托": "quest_daily",
        "魔神任务": "quest_archon",
        "传说任务": "quest_story",
        "邀约事件": "quest_story",
        "世界任务": "quest_world",
        "活动任务": "quest_event",
        "追踪任务": "quest_track",
        "过场动画": "quest_skip_cutscene",
        "对话": "quest_dialog",
        # English quest
        "advance dialog": "quest_dialog",
        "dialog select": "quest_dialog_select",
        "track quest": "quest_track",
        "skip cutscene": "quest_skip_cutscene",
        "quest log": "quest_read_log",
        "daily commission": "quest_daily",
        "archon quest": "quest_archon",
        "story quest": "quest_story",
        "hangout event": "quest_story",
        "world quest": "quest_world",
        "event quest": "quest_event",
        "cutscene": "quest_skip_cutscene",
        # Genshin character progression chain (6-stage ordered sequence)
        "角色养成": "progression_chain",
        "养成链": "progression_chain",
        "完整养成": "progression_chain",
        "养成阶段一": "progression_level_up",
        "养成阶段二": "progression_ascend",
        "养成阶段三": "progression_weapon",
        "养成阶段四": "progression_artifact",
        "养成阶段五": "progression_talent",
        "养成阶段六": "progression_party",
        "升级到40": "progression_level_up",
        "突破到90": "progression_ascend",
        "配武器": "progression_weapon",
        "配圣遗物": "progression_artifact",
        "升天赋": "progression_talent",
        "配队伍": "progression_party",
        # English progression chain
        "progression chain": "progression_chain",
        "character build": "progression_chain",
        "full build": "progression_chain",
        "build weapon": "progression_weapon",
        "build artifact": "progression_artifact",
        "build talent": "progression_talent",
        "build party": "progression_party",
        # Genshin daily routine
        "消耗树脂": "daily_resin",
        "秘境": "daily_domain",
        "天赋秘境": "daily_domain",
        "圣遗物秘境": "daily_domain",
        "武器秘境": "daily_domain",
        "浓缩树脂": "daily_resin",
        "凯瑟琳奖励": "daily_katheryne",
        "领取奖励": "daily_katheryne",
        "探索派遣": "daily_expedition",
        "派遣回收": "daily_expedition",
        "尘歌壶": "daily_pot",
        "宝钱": "daily_pot",
        "速通日常": "daily_quick",
        "标准日常": "daily_standard",
        "深度日常": "daily_deep",
        # English daily routine
        "spend resin": "daily_resin",
        "domain run": "daily_domain",
        "domain farm": "daily_domain",
        "artifact domain": "daily_domain",
        "talent domain": "daily_domain",
        "condensed resin": "daily_resin",
        "katheryne reward": "daily_katheryne",
        "claim reward": "daily_katheryne",
        "expedition check": "daily_expedition",
        "serenitea pot": "daily_pot",
        "quick daily": "daily_quick",
        "standard daily": "daily_standard",
        "deep daily": "daily_deep",
        # Genshin long-chain scenarios
        "新手教程": "chain_tutorial",
        "新手链": "chain_tutorial",
        "tutorial": "chain_tutorial",
        "新手引导": "chain_tutorial",
        "日常会话": "chain_daily_session",
        "15分钟日常": "chain_daily_session",
        "快速日常链": "chain_daily_session",
        "daily session": "chain_daily_session",
        "boss连战": "chain_boss_gauntlet",
        "boss试炼": "chain_boss_gauntlet",
        "boss gauntlet": "chain_boss_gauntlet",
        "周本连战": "chain_weekly_gauntlet",
        "weekly gauntlet": "chain_weekly_gauntlet",
        "探索清剿": "chain_exploration_sweep",
        "区域清剿": "chain_exploration_sweep",
        "exploration sweep": "chain_exploration_sweep",
        "养成全流程": "progression_chain",
        "角色满配": "progression_chain",
        # Genshin mainline quest progression
        "主线推进": "mainline_progress",
        "魔神任务推进": "mainline_progress",
        "推进主线": "mainline_progress",
        "序章": "mainline_prologue",
        "第一章": "mainline_ch1",
        "第二章": "mainline_ch2",
        "第三章": "mainline_ch3",
        "第四章": "mainline_ch4",
        "第五章": "mainline_ch5",
        "prologue": "mainline_prologue",
        "chapter 1": "mainline_ch1",
        "chapter 2": "mainline_ch2",
        "chapter 3": "mainline_ch3",
        "chapter 4": "mainline_ch4",
        "chapter 5": "mainline_ch5",
        "mainline": "mainline_progress",
        # Honkai: Star Rail — HSR-specific phrases (must come before generic "combat")
        "进入战斗": "hsr_combat",
        "hsr combat": "hsr_combat",
        "星穹战斗": "hsr_combat",
        "combat": "hsr_combat",
        "hsr dialog": "hsr_dialog",
        "星穹对话": "hsr_dialog",
        "navigate": "hsr_navigate",
        "导航": "hsr_navigate",
    }

    def resolve(self, text: str) -> TaskSpecResult:
        text_lower = text.lower()
        # Sort by keyword length descending — longest match wins
        for keyword, capability in sorted(
            self._KEYWORDS.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            if keyword in text_lower:
                return TaskSpecResult(
                    task_id=f"task_{uuid.uuid4().hex[:8]}",
                    capability=capability,
                    success_criteria=f"capability={capability} completed",
                )
        return TaskSpecResult(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            capability="unknown",
            confidence=0.3,
        )


class SimpleSkillRecipeLookup:
    """Lookup that maps capabilities to SkillRecipes."""

    def __init__(self, recipes: dict[str, SkillRecipe] | None = None) -> None:
        self._recipes = recipes or {}

    def register(self, capability: str, recipe: SkillRecipe) -> None:
        self._recipes[capability] = recipe

    def lookup(self, capability: str) -> SkillRecipe | None:
        return self._recipes.get(capability)

    def find_applicable(self, context: str, goal: Any) -> list[SkillRecipe]:
        """Find recipes whose capability or goal_id matches the context/goal."""
        results: list[SkillRecipe] = []
        goal_id = getattr(goal, "goal_id", str(goal)).lower()
        context_lower = context.lower()
        for cap, recipe in self._recipes.items():
            if goal_id in cap or cap in goal_id or context_lower in cap:
                results.append(recipe)
        return results

    @classmethod
    def with_default_ui_flows(cls) -> SimpleSkillRecipeLookup:
        """Create a lookup pre-populated with standard UI flow capabilities."""
        lookup = cls()
        _UI_CAPABILITY_MAP: dict[str, tuple[str, str]] = {
            "character_level_up": ("character_level_up_full", "genshin"),
            "character_ascend": ("character_ascend_full", "genshin"),
            "talent_upgrade": ("character_talent_upgrade_full", "genshin"),
            "weapon_equip": ("weapon_equip_full", "genshin"),
            "weapon_enhance": ("weapon_enhance_full", "genshin"),
            "weapon_refine": ("weapon_refine_full", "genshin"),
            "artifact_equip": ("artifact_equip_full", "genshin"),
            "artifact_enhance": ("artifact_enhance_full", "genshin"),
            "wish_pull": ("wish_ten_pull_full", "genshin"),
            # Combat capabilities
            "combat_basic": ("combat_basic", "genshin"),
            "combat_shield_break": ("combat_shield_break", "genshin"),
            "combat_boss": ("combat_boss", "genshin"),
            "combat_abyss_mage": ("combat_abyss_mage", "genshin"),
            "combat_world_boss": ("combat_world_boss", "genshin"),
            "combat_weekly": ("combat_weekly", "genshin"),
            # Boss-specific combat
            "combat_boss_dvalin": ("combat_boss_dvalin", "genshin"),
            "combat_boss_childe": ("combat_boss_childe", "genshin"),
            "combat_boss_signora": ("combat_boss_signora", "genshin"),
            "combat_boss_raiden": ("combat_boss_raiden", "genshin"),
            "combat_boss_shouki": ("combat_boss_shouki", "genshin"),
            "combat_boss_narwhal": ("combat_boss_narwhal", "genshin"),
            # Environment combat
            "combat_env_dragonspine": ("combat_env_dragonspine", "genshin"),
            "combat_env_inazuma": ("combat_env_inazuma", "genshin"),
            # Abyss
            "combat_abyss": ("combat_abyss_floor", "genshin"),
            # Multi-wave
            "combat_multi_wave": ("combat_multi_wave", "genshin"),
            # Rotations
            "combat_weekly_rotation": ("combat_weekly_rotation", "genshin"),
            "combat_world_farming": ("combat_world_farming", "genshin"),
            # Exploration capabilities
            "explore_waypoint": ("explore_activate_waypoint", "genshin"),
            "explore_statue": ("explore_activate_statue", "genshin"),
            "explore_chest": ("explore_open_chest", "genshin"),
            "explore_oculus": ("explore_collect_oculus", "genshin"),
            "explore_puzzle": ("explore_puzzle", "genshin"),
            "explore_timed": ("explore_timed_challenge", "genshin"),
            "explore_withering": ("explore_withering_zone", "genshin"),
            "explore_underwater": ("explore_underwater", "genshin"),
            # Quest capabilities
            "quest_dialog": ("quest_dialog", "genshin"),
            "quest_dialog_select": ("quest_dialog_select", "genshin"),
            "quest_track": ("quest_track", "genshin"),
            "quest_skip_cutscene": ("quest_skip_cutscene", "genshin"),
            "quest_read_log": ("quest_read_log", "genshin"),
            "quest_daily": ("quest_daily_commission", "genshin"),
            "quest_archon": ("quest_archon", "genshin"),
            "quest_story": ("quest_story", "genshin"),
            "quest_world": ("quest_world", "genshin"),
            "quest_event": ("quest_event", "genshin"),
            # Daily routine capabilities
            "daily_resin": ("daily_resin", "genshin"),
            "daily_domain": ("daily_domain", "genshin"),
            "daily_katheryne": ("daily_katheryne", "genshin"),
            "daily_expedition": ("daily_expedition", "genshin"),
            "daily_pot": ("daily_pot", "genshin"),
            "daily_quick": ("daily_quick", "genshin"),
            "daily_standard": ("daily_standard", "genshin"),
            "daily_deep": ("daily_deep", "genshin"),
            # Character progression chain
            "progression_chain": ("progression_chain", "genshin"),
            "progression_level_up": ("progression_level_up", "genshin"),
            "progression_ascend": ("progression_ascend", "genshin"),
            "progression_weapon": ("progression_weapon", "genshin"),
            "progression_artifact": ("progression_artifact", "genshin"),
            "progression_talent": ("progression_talent", "genshin"),
            "progression_party": ("progression_party", "genshin"),
            # Long-chain scenarios
            "chain_tutorial": ("chain_tutorial", "genshin"),
            "chain_daily_session": ("chain_daily_session", "genshin"),
            "chain_boss_gauntlet": ("chain_boss_gauntlet", "genshin"),
            "chain_weekly_gauntlet": ("chain_weekly_gauntlet", "genshin"),
            "chain_exploration_sweep": ("chain_exploration_sweep", "genshin"),
            # Mainline quest progression
            "mainline_progress": ("mainline_progress", "genshin"),
            "mainline_prologue": ("mainline_prologue", "genshin"),
            "mainline_ch1": ("mainline_ch1", "genshin"),
            "mainline_ch2": ("mainline_ch2", "genshin"),
            "mainline_ch3": ("mainline_ch3", "genshin"),
            "mainline_ch4": ("mainline_ch4", "genshin"),
            "mainline_ch5": ("mainline_ch5", "genshin"),
        }
        for capability, (skill_id, capsule_id) in _UI_CAPABILITY_MAP.items():
            lookup.register(capability, SkillRecipe(
                skill_id=skill_id,
                capsule_id=capsule_id,
            ))
        return lookup


class SimpleScreenClaimProvider:
    """ScreenClaim provider using ScreenStateClaimBuilder."""

    def __init__(self, claim_builder: ScreenStateClaimBuilder | None = None,
                 frame_supplier: Any = None) -> None:
        self._builder = claim_builder or ScreenStateClaimBuilder()
        self._frame_supplier = frame_supplier

    def build_claim(self) -> ScreenClaimResult:
        frame = None
        if self._frame_supplier is not None:
            try:
                frame = self._frame_supplier()
            except Exception:
                pass
        if frame is None:
            return ScreenClaimResult(
                claim_id=f"claim_{uuid.uuid4().hex[:8]}",
                screen_state="unknown",
                confidence=0.0,
            )
        try:
            claim = self._builder.build(frame, observation=None)
            return ScreenClaimResult(
                claim_id=claim.claim_id if hasattr(claim, "claim_id") else f"claim_{uuid.uuid4().hex[:8]}",
                screen_state=claim.screen_state if hasattr(claim, "screen_state") else "unknown",
                ui_elements={e.name: {"bbox": e.bbox} for e in claim.ui_elements} if hasattr(claim, "ui_elements") else {},
                confidence=claim.confidence if hasattr(claim, "confidence") else 0.5,
                raw_frame=frame,
            )
        except Exception as exc:
            log.debug("[ScreenClaimProvider] build failed: %s", exc)
            return ScreenClaimResult(
                claim_id=f"claim_{uuid.uuid4().hex[:8]}",
                screen_state="error",
                confidence=0.0,
            )


class SimpleOverridePolicyValidator:
    """Basic override validator: rejects critical and permanent overrides."""

    def validate(self, override: RuntimeOverrideClaim) -> RuntimeOverrideClaim:
        if override.risk_level == "critical":
            return override.reject("critical overrides require human confirmation")
        if override.scope == "permanent":
            return override.reject("permanent overrides require CapsulePatchProposal")
        if override.confidence < 0.3:
            return override.reject("confidence too low")
        return override.validate()


class ReceiptVerificationProvider:
    """Verify based on ExecutionRuntime PhysicalReceipt."""

    def verify(self, task: TaskSpecResult, screen: ScreenClaimResult) -> VerificationResult:
        return VerificationResult(
            verified=False,
            confidence=0.0,
            method="none",
            details="receipt_verification_requires_explicit_call",
        )


class VLMVerificationProvider:
    """Verify post-action state via VLM analysis.

    In production, this calls the VLM to check whether the expected state
    change occurred. Falls back to self-assertion when VLM is unavailable.
    """

    def __init__(self, vlm_fn: Any | None = None, frame_supplier: Any = None) -> None:
        self._vlm_fn = vlm_fn
        self._frame_supplier = frame_supplier

    def verify(self, task: TaskSpecResult, screen: ScreenClaimResult) -> VerificationResult:
        if self._vlm_fn is None or self._frame_supplier is None:
            return VerificationResult(
                verified=False,
                confidence=0.0,
                method="none",
                details="no_vlm_available",
            )
        frame = None
        try:
            frame = self._frame_supplier()
        except Exception:
            pass
        if frame is None:
            return VerificationResult(
                verified=False,
                confidence=0.0,
                method="none",
                details="no_frame_for_verification",
            )
        try:
            prompt = f"Did the action '{task.capability}' complete successfully? Check if the expected state change occurred."
            result = self._vlm_fn(frame, prompt=prompt)
            if isinstance(result, dict):
                ok = result.get("success", False)
                conf = float(result.get("confidence", 0.5))
                return VerificationResult(
                    verified=bool(ok),
                    confidence=conf,
                    method="vlm",
                    details=result.get("reasoning", ""),
                )
            return VerificationResult(
                verified=False,
                confidence=0.0,
                method="vlm",
                details="unexpected_vlm_response",
            )
        except Exception as exc:
            return VerificationResult(
                verified=False,
                confidence=0.0,
                method="vlm",
                details=f"vlm_error: {exc}",
            )


# ---------------------------------------------------------------------------
# ClosedLoopRunner
# ---------------------------------------------------------------------------

class ClosedLoopRunner:
    """Orchestrate the minimal autonomy closed loop.

    Usage::

        runner = ClosedLoopRunner(skill_adapter=adapter)
        result = runner.run("升级胡桃到90级")
    """

    def __init__(
        self,
        *,
        execution_runtime: ExecutionRuntime | None = None,
        skill_adapter: Any | None = None,
        task_resolver: TaskSpecResolver | None = None,
        skill_lookup: SkillRecipeLookup | None = None,
        screen_provider: ScreenClaimProvider | None = None,
        claim_graph: ClaimGraph | None = None,
        override_validator: OverridePolicyValidator | None = None,
        verification_provider: VerificationProvider | None = None,
    ) -> None:
        self._exec_runtime = execution_runtime
        self._skill_adapter = skill_adapter
        self._task_resolver = task_resolver or SimpleTaskSpecResolver()
        self._skill_lookup = skill_lookup or SimpleSkillRecipeLookup()
        self._screen_provider = screen_provider or SimpleScreenClaimProvider()
        self._claim_graph = claim_graph or ClaimGraph()
        self._override_validator = override_validator or SimpleOverridePolicyValidator()
        self._verification = verification_provider

    def run(self, companion_text: str) -> ClosedLoopResult:
        """Execute the full closed loop from companion text to verified result."""
        loop_id = f"loop_{uuid.uuid4().hex[:8]}"
        start = time.perf_counter()
        steps: list[LoopStepResult] = []

        # Step 1: TaskSpec resolution
        step_result = self._step_resolve_task(companion_text)
        steps.append(step_result)
        if not step_result.success:
            return self._finish(loop_id, step_result.details, False, start, steps)
        task: TaskSpecResult = step_result.details

        # Step 2: SkillRecipe lookup
        step_result = self._step_lookup_skill(task)
        steps.append(step_result)
        if not step_result.success:
            return self._finish(loop_id, f"no_skill_for:{task.capability}", False, start, steps)
        recipe: SkillRecipe = step_result.details

        # Step 3: ScreenClaim (pre-action)
        step_result = self._step_build_screen_claim()
        steps.append(step_result)
        screen_claim: ScreenClaimResult = step_result.details

        # Step 4: ActionContract → ExecutionRuntime (dry-run or real)
        step_result = self._step_execute(recipe, task, screen_claim)
        steps.append(step_result)
        execution_succeeded = step_result.success
        receipt: PhysicalReceipt | None = step_result.receipt

        # Step 5: Post-action ObservationClaim + StateDeltaClaim
        step_result = self._step_verify(receipt, task, recipe, execution_succeeded, screen_claim)
        steps.append(step_result)

        success = step_result.success
        return self._finish(loop_id, task.task_id, success, start, steps)

    def apply_override(self, override: RuntimeOverrideClaim) -> RuntimeOverrideClaim:
        """Validate and apply a runtime override."""
        validated = self._override_validator.validate(override)
        if validated.status != "validated":
            return validated
        return validated.apply()

    def propose_patch(self, patch: CapsulePatchProposal) -> CapsulePatchProposal:
        """Process a capsule patch proposal through validation pipeline.

        Note: replay verification requires actual replay execution by the caller.
        This method handles schema and diff stages only.
        """
        patch = patch.with_schema_validated()
        patch = patch.with_diff_reviewed()
        # Caller must run actual replay and call patch.with_replay_verified(result)
        return patch

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _step_resolve_task(self, text: str) -> LoopStepResult:
        started = time.perf_counter()
        try:
            result = self._task_resolver.resolve(text)
            ok = result.capability != "unknown"
            return LoopStepResult(
                step="resolve_task",
                success=ok,
                duration_ms=(time.perf_counter() - started) * 1000,
                details=result if ok else f"unknown_capability_from: {text[:50]}",
            )
        except Exception as exc:
            return LoopStepResult(
                step="resolve_task",
                success=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                details=f"error: {exc}",
            )

    def _step_lookup_skill(self, task: TaskSpecResult) -> LoopStepResult:
        started = time.perf_counter()
        recipe = self._skill_lookup.lookup(task.capability)
        if recipe is None:
            return LoopStepResult(
                step="lookup_skill",
                success=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                details=f"no_recipe_for: {task.capability}",
            )
        return LoopStepResult(
            step="lookup_skill",
            success=True,
            duration_ms=(time.perf_counter() - started) * 1000,
            details=recipe,
        )

    def _step_build_screen_claim(self) -> LoopStepResult:
        started = time.perf_counter()
        claim = self._screen_provider.build_claim()
        return LoopStepResult(
            step="screen_claim",
            success=claim.confidence > 0.0,
            duration_ms=(time.perf_counter() - started) * 1000,
            details=claim,
        )

    def _step_execute(
        self, recipe: SkillRecipe, task: TaskSpecResult, screen: ScreenClaimResult,
    ) -> LoopStepResult:
        started = time.perf_counter()

        # Priority 1: Use UIFlowSkillAdapter for skill-based actions
        if self._skill_adapter is not None:
            return self._execute_via_adapter(recipe, task, started)

        # Priority 2: Use ExecutionRuntime for raw input actions
        if self._exec_runtime is not None:
            return self._execute_via_runtime(recipe, task, screen, started)

        return LoopStepResult(
            step="execute",
            success=False,
            duration_ms=(time.perf_counter() - started) * 1000,
            details="no_execution_backend",
        )

    def _execute_via_adapter(
        self, recipe: SkillRecipe, task: TaskSpecResult, started: float,
    ) -> LoopStepResult:
        """Execute skill through UIFlowSkillAdapter."""
        try:
            ok = self._skill_adapter.execute_semantic(
                action=recipe.skill_id,
                target=task.target,
                context={**recipe.parameters, **task.parameters},
            )
            return LoopStepResult(
                step="execute",
                success=ok,
                duration_ms=(time.perf_counter() - started) * 1000,
                details=f"adapter:{recipe.skill_id} ok={ok}",
            )
        except Exception as exc:
            return LoopStepResult(
                step="execute",
                success=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                details=f"adapter_error: {exc}",
            )

    def _execute_via_runtime(
        self, recipe: SkillRecipe, task: TaskSpecResult,
        screen: ScreenClaimResult, started: float,
    ) -> LoopStepResult:
        """Execute skill through ExecutionRuntime (raw input pipeline)."""
        action_id = f"action_{uuid.uuid4().hex[:8]}"
        semantic_action = SemanticAction(
            action_id=action_id,
            kind="skill",
            intent=recipe.skill_id,
            target=task.target,
            parameters={**recipe.parameters, **task.parameters},
            requires_physical_input=True,
        )
        contract = ActionContract(
            action_id=action_id,
            semantic_action=semantic_action,
            safety_policy={
                "require_focus": True,
                "input_lease_required": True,
                "max_lease_ms": 5000,
            },
            timeout_ms=5000,
            risk_level=recipe.risk_level,
        )

        try:
            receipt = self._exec_runtime.submit(
                semantic_action, contract, post_action_frame=screen.raw_frame,
            )
            return LoopStepResult(
                step="execute",
                success=receipt.success,
                duration_ms=(time.perf_counter() - started) * 1000,
                details=receipt.reason,
                receipt=receipt,
            )
        except Exception as exc:
            return LoopStepResult(
                step="execute",
                success=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                details=f"execution_error: {exc}",
            )

    def _step_verify(
        self, receipt: PhysicalReceipt | None, task: TaskSpecResult,
        recipe: SkillRecipe, execution_succeeded: bool = False,
        screen: ScreenClaimResult | None = None,
    ) -> LoopStepResult:
        started = time.perf_counter()

        # Build observation claim
        obs = ObservationClaim(
            observation_id=f"obs_{uuid.uuid4().hex[:8]}",
            claim_id=f"obsclaim_{uuid.uuid4().hex[:8]}",
            source_family="closed_loop",
            polarity="support",
            signal_quality=0.8,
            confidence=0.8,
        )
        self._claim_graph.add_observation(obs)

        # Determine verification method (priority order)
        vmethod = "none"
        vconfidence = 0.0
        vdetails = ""

        # 1. ExecutionRuntime receipt verification (strongest)
        if receipt is not None and receipt.is_verified:
            vmethod = "receipt"
            vconfidence = 0.9
            vdetails = "receipt_verified"
        # 2. VLM/OCR verification provider (observation-based)
        elif self._verification is not None and screen is not None:
            vr = self._verification.verify(task, screen)
            if vr.method != "none":
                vmethod = vr.method
                vconfidence = vr.confidence
                vdetails = vr.details
        # 3. Adapter self-assertion (weakest — tagged explicitly)
        elif execution_succeeded and receipt is None:
            vmethod = "self_assert"
            vconfidence = 0.3
            vdetails = "adapter_success_no_observation"

        verified = vconfidence >= 0.5

        delta = StateDeltaClaim(
            claim_id=f"delta_{uuid.uuid4().hex[:8]}",
            mission_id=task.task_id,
            node_id=recipe.skill_id,
            skill_id=recipe.skill_id,
            claim_type="action_result",
            claimed_delta={
                "capability": task.capability,
                "verified": verified,
                "method": vmethod,
            },
            status="verified" if verified else "asserted",
            confidence=vconfidence,
            evidence_refs=[obs.observation_id],
        )
        self._claim_graph.add_claim(delta)

        return LoopStepResult(
            step="verify",
            success=verified,
            duration_ms=(time.perf_counter() - started) * 1000,
            details=f"claim={delta.claim_id} status={delta.status} method={vmethod} conf={vconfidence:.2f}",
            claim=delta,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _finish(
        loop_id: str, task_id: str, success: bool,
        start: float, steps: list[LoopStepResult],
    ) -> ClosedLoopResult:
        return ClosedLoopResult(
            loop_id=loop_id,
            task_id=task_id,
            success=success,
            total_duration_ms=(time.perf_counter() - start) * 1000,
            steps=tuple(steps),
            final_state="success" if success else "failed",
        )

    @property
    def claim_graph(self) -> ClaimGraph:
        return self._claim_graph

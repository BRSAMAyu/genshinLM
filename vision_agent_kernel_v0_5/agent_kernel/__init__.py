"""AgentKernel — generic agent perception-decision-execution framework.

This package defines the core protocols and data types for building
vision-driven autonomous agents. It is game-agnostic; application-specific
logic lives in adapter packages.

Architecture layers (L0-L9):
  L0   InputLeaseManager     — physical safety, lease management
  L1-2 SpinalReflexAgent     — combat reflex, threat evaluation
  L3-4 BrainstemNavigator    — PID navigation, stuck detection
  L3-4 DialogueController    — smart dialogue skip + branch intercept
  L5-6 CerebellumController  — DesktopTree, OCR, route compilation
  L7-8 CerebrumAgent         — mission compilation, failure diagnosis
  L9   CompanionAgent        — user interaction, override handling
"""
from __future__ import annotations

from agent_kernel.types import (
    ActionableElement,
    ActionPlan,
    ActionPrimitive,
    Affordance,
    AgentGoal,
    CapsulePatchProposal,
    ClaimEvidence,
    Experience,
    GoalResult,
    OperatorCommand,
    PlannedStep,
    RuntimeOverride,
    SceneGraph,
    SceneObject,
    SemanticObservation,
    SkillRecipe,
    SkillStep,
    StateDeltaClaim,
    StepResult,
    TaskSpec,
)
from agent_kernel.protocols import (
    BrainstemNavigator,
    CerebellumController,
    CerebrumAgent,
    ClaimAdjudicator,
    CompanionAgent,
    DialogueController,
    ExecutionProvider,
    InputLeaseManager,
    MemoryStore,
    PerceptionProvider,
    Planner,
    SkillRecipeLookup,
    SpinalReflexAgent,
    SuccessChecker,
)

__all__ = [
    # Types
    "ActionableElement",
    "ActionPlan",
    "ActionPrimitive",
    "Affordance",
    "AgentGoal",
    "CapsulePatchProposal",
    "ClaimEvidence",
    "Experience",
    "GoalResult",
    "OperatorCommand",
    "PlannedStep",
    "RuntimeOverride",
    "SceneGraph",
    "SceneObject",
    "SemanticObservation",
    "SkillRecipe",
    "SkillStep",
    "StateDeltaClaim",
    "StepResult",
    "TaskSpec",
    # Protocols
    "BrainstemNavigator",
    "CerebellumController",
    "CerebrumAgent",
    "ClaimAdjudicator",
    "CompanionAgent",
    "DialogueController",
    "ExecutionProvider",
    "InputLeaseManager",
    "MemoryStore",
    "PerceptionProvider",
    "Planner",
    "SkillRecipeLookup",
    "SpinalReflexAgent",
    "SuccessChecker",
]

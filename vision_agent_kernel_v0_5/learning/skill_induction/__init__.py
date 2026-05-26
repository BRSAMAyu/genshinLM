"""Skill Induction v2 — full pipeline from traces to promoted skills.

Pipeline stages:
  TraceRecorder → EpisodeSegmenter → AnchorBinder → PromotionGate → SkillRegistry

Hard rules:
- Coordinate-only traces stay at raw_trace tier, never promote
- Skills without produced_claims cannot enter candidate
- Skills without verifiers on terminal claims cannot be unattended
- New skill priors are for ranking only, not safety gating
"""

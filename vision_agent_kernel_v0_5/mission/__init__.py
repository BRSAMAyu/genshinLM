"""Phase 5 mission orchestration — claim-gated node graph (ROADMAP Phase 5).

Generalizes the linear daily-commission sequencing (Phase 3) into a real mission
graph: nodes with dependencies, each claim-gated (precondition verified -> execute
-> postcondition verified -> checkpoint). On node failure the orchestrator
attributes the cause and recovers/replans rather than aborting the whole mission,
previewing the BAGEL attribution + MainlineRunner behaviour the north-star needs.
"""

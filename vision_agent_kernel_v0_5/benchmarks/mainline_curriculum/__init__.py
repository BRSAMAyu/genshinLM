"""Benchmark Curriculum — structured capability assessment.

Tasks from C0 to C11 measure progressive capability:
  C0: Bootstrap startup (system init, claim graph, BAGEL ready)
  C1: Dialogue progression (advance dialogue, select options)
  C2: Quest tracking (detect objective changes, context updates)
  C3: Map teleport (open map, select waypoint, verify arrival)
  C4: Short navigation (heading servo to nearby target)
  C5: Interaction collect (interact with NPC/item, claim pickup)
  C6: Basic combat (engage, survive, kill)
  C7: Recovery gauntlet (survive all recovery recipes)
  C8: Skill induction (learn new skill from unknown UI)
  C9: Multi-node mainline (complete 5+ node mission)
  C10: Boss failure revision (fail, attribute, revise, succeed)
  C11: Long horizon 2h resume (checkpoint, stop, resume)
"""

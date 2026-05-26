"""Sentinel Protocol — persistent recovery watchdog.

Sentinel monitors the agent's somatic state and triggers recovery recipes
when anomalies are detected. Recipes must:
- Check preconditions before executing
- Execute recovery with bounded budget
- Verify restabilization after recovery
- Write claims and BAGEL feedback on completion or failure
"""

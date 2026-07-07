---
name: web-app-remembered-facts
description: Facts remembered via the GarminCoach web app chat (remember_fact tool / POST /remember) - auto-appended by server.py, not hand-edited
metadata:
  node_type: memory
  type: project
---

## Web App Facts

Append-only log. Each entry is auto-committed by `server.py`'s `_append_to_context()`
when a fact is remembered via the chat `remember_fact` tool or `POST /remember`.
Distinct from the hand-curated files in this directory (`race_goals_2026.md`,
`training_history.md`, `home_gym_equipment.md`, `hr_zones.md`) - those are
deliberately written and reorganized by Claude Code sessions; this file is a
running record from the web app only. If an entry here turns out to be
durable/important, fold it into the relevant curated file by hand and remove
it from here.

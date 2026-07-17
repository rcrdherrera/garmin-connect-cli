---
name: home-gym-equipment
description: Available home gym equipment for workout prescription; must be respected in all strength session design
metadata: 
  node_type: memory
  type: project
  originSessionId: dc5f9c3f-0963-411c-bac0-469713a060b4
---

## Equipment Inventory

Canonical machine-readable list: `data/my_equipment.json` — update both together.

- Dumbbells: pair, up to 10kg each
- Kettlebells: pair, up to 10kg each
- Flat bench
- Elastic bands (resistance bands, tube-style)
- Tibial bar (tibialis anterior raises)
- Incline bench / slant board for feet (used with tibial bar)
- Ankle/foot dumbbell strap (TOPJUM) — anchors a DB to the top of the foot for weighted open-chain leg work
- Fabric hip resistance loops ×3 (light / medium / heavy) — worn above the knees

`src/garmin_connect_cli/workout_builder.py`'s `validate_exercise()` checks any exercise's equipment requirement (from `data/garmin_exercises_equipment.json`) against `data/my_equipment.json`'s owned list automatically — use it instead of manually cross-referencing this file when building a workout.

## No Bar

No pull-up bar. Replace any pull-up/chin-up prescriptions with:
- Single-arm DB row (bench-supported, 10kg) — same lat/rhomboid recruitment
- Band face pull — rear delt + external rotation

## Key Uses by Equipment

- KB/DB (up to 10kg each): load compound movements — split squat, reverse lunge, RDL, walking lunge, step-up, calf raise, glute bridge
- Bench: step-ups, single-arm row support, incline push-up variations
- Elastic bands: face pulls, band pull-aparts, banded rows
- Tibial bar + incline bench: tibialis anterior raises (3×15, 3s eccentric) — critical for PTT/pronation control; include in every lower body session
- Ankle/foot DB strap: weighted hip-flexor raises, leg extensions, standing/lying hamstring curls, glute kickbacks — adds load to open-chain single-joint leg work the DBs/KBs can't easily target
- Fabric hip loops (light/med/heavy): glute-medius/abductor work — banded squats, lateral & monster walks, clamshells, banded glute bridge, fire hydrants. Progress light→heavy.

**Why:** Tibialis anterior eccentrically controls pronation on every footstrike. With the PTT history and return-to-run phase, tibial bar raises belong in every lower body session alongside eccentric calf raises. **Hip-loop abductor work is equally PTT-relevant** — weak hip abductors → excessive femoral internal rotation → pronation → PTT overload (Semciw et al.), so band walks/clamshells earn a place in lower sessions too. See [[strength-scheduling-framework]] for how these sessions are placed around the run calendar.

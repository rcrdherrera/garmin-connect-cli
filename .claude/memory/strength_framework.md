---
name: strength-scheduling-framework
description: How to place and build strength sessions around the run calendar during the marathon build — frequency, day placement, and which library templates to schedule
metadata:
  node_type: memory
  type: project
---

## Placement rules (concurrent strength + endurance)

Strength is scheduled *around* the run calendar, not independently. See run days first with `garmin-connect --format json calendar show --month YYYY-MM` (one row/day, `workouts`=scheduled, `activities`=completed; or `client.get_calendar_month(year, month)` for raw items incl. workout/scheduled IDs). Then place strength by these rules:

1. **Hard days hard** — stack **lower-body** strength on a **quality-run day** (e.g. Tuesday), not on a rest day. Concentrates stress so genuine recovery days stay recovery days.
2. **Protect the long run** — no lower-body strength in the 48h *before* the Saturday long run. Friday stays clear.
3. **Upper body is leg-cheap** — place **upper + core** on an **easy-run day** (e.g. Thursday); it doesn't compromise long-run freshness.
4. **Frequency = 2×/week during the marathon build** (Phase 4+, 40–52 km/week). This is the maintenance dose — retains strength/tendon resilience without the fatigue that spiked TSB to −31 after the half. 3× (adding full-body posterior chain) only on a fully-recovered week. Phase 1's 3×/week applied when running volume was ~15 km/week.
5. **Skip strength on deep-fatigue weeks** — if TSB < −20 or readiness LOW (e.g. the week after a race), don't add strength; recovery takes priority.

Canonical week during the build: **Tue = Lower+PTT (quality day) · Thu = Upper+Core (easy day) · Fri clear · Sat long run.**

## Which library templates to schedule (reuse, don't re-upload)

Do **not** upload new strength dicts (see [[feedback-workout-upload]] — validation gate). These existing templates are already validated and render correctly:

- **Lower body → `1633885839` "Lower Body: Hip, Glute, Tibialis & Bands — PTT Focus"** — the current lower template (builder: `lower_body_hip_glute_bands()` in `create_workouts.py`). 8 exercises: lateral band walk (hip loop, glute-med), glute bridge 10kg, single-leg hip raise, split squat 8kg, reverse lunge 8kg, weighted lying leg raise 4kg (ankle strap, hip flexor), standing calf raise 10kg (3s ecc), tibialis raise (tibial bar, 3s ecc). Uses the hip bands + ankle strap from [[home-gym-equipment]]. Supersedes `1579706543` (no bands/strap, and its weights were stored as grams so displayed ~1000× too heavy) and `1585168279` (no tibialis).
- **Upper body → `1579706556` "Upper Body + Core: Running Economy"** — push-up, pike push-up, DB row, band face-pull, plank, side plank, sit-up. Fits the DB+bands, no-bar setup (uses rows/face-pulls instead of pull-ups).
- Avoid `1607173029` ("Stability & Strength") — prescribes a single-leg **barbell** deadlift; no barbell owned.

Schedule via `client.schedule_workout(workout_id, "YYYY-MM-DD")` (GarminClient wrapper, not raw garminconnect).

## Tracking

Completed strength sessions sync into `garmin.db` automatically and appear in `analyze` (strength block: session count, avg/total load) and `evaluate`. No separate logging needed — the watch executes the scheduled workout, and it lands in the same DB the coaching skills read. This closes the gap where phone-Claude lacked training context.

See [[home-gym-equipment]] for the equipment constraints every strength session must respect, [[race_goals_2026]] for phase structure, and [[hr_zones]] for the run-intensity anchors.

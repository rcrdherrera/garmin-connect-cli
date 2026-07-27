---
name: feedback-workout-upload
description: Upload to Garmin is disabled for now; workout dict must match Garmin exercise library before re-enabling
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9076a27c-98cf-4a04-8bed-d037ce68977d
---

**SUPERSEDED (2026-07-18).** The blanket "upload disabled" rule below is obsolete — it predates `workout_builder.validate_exercise()`, which is exactly the validation gate this note was waiting for. Uploading is now the normal, working practice **as long as every exercise is validated first**: it checks each `(category, name)` against Garmin's FIT catalog (`data/garmin_exercises_equipment.json`) AND owned equipment (`data/my_equipment.json`), falling back to `category=None, name=None` on any warning. Templates `1633885839` (Lower PTT, session 12) and `1635454203` (PTT prehab, this session) were both uploaded and scheduled cleanly via `client.upload_workout()` → `client.schedule_workout()` through this gate. See [[strength-scheduling-framework]].

The current rule, restated: **do not upload UN-validated dicts** — always run `validate_exercise()` on every exercise before building the step. That's the whole gate.

---

_Original note (kept for history):_ Do NOT upload workouts to Garmin Connect in coaching sessions until the exercise dictionary is validated against Garmin's FIT SDK library. **Why:** The current workout dict uses exercise category/name values that may not match Garmin's verified library. **How to apply:** generate the dict and print it for review; re-enable upload only after a validated mapping exists — now provided by `validate_exercise()`.

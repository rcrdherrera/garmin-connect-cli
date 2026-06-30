---
name: feedback-workout-upload
description: Upload to Garmin is disabled for now; workout dict must match Garmin exercise library before re-enabling
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9076a27c-98cf-4a04-8bed-d037ce68977d
---

Do NOT upload workouts to Garmin Connect in coaching sessions until the exercise dictionary is validated against Garmin's FIT SDK library.

**Why:** The current workout dict uses exercise category/name values that may not match Garmin's verified library (e.g., custom exercises like tibial raises have no Garmin FIT equivalent, and pull/row exercises outside the verified list are unverified). Uploading unverified dicts wastes calendar slots and requires cleanup.

**How to apply:** In coach sessions, generate the workout dict and print it (or save to file) for review. Re-enable upload only after we have a validated mapping of all exercises to Garmin's FIT SDK names. The upload block pattern is:
```python
result = client.client.upload_workout(w)
workout_id = result.get("workoutId")
schedule_result = client.schedule_workout(workout_id, "YYYY-MM-DD")
```
Keep this commented out or absent until further notice.

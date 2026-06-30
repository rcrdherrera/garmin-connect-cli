import sys, json
sys.path.insert(0, r"C:\garmin-connect-cli\src")
from garmin_connect_cli.client import GarminClient
from garmin_connect_cli.config import Config

config = Config.load()
client = GarminClient(config)
client.ensure_authenticated()

STRENGTH  = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
REPS_COND = {"conditionTypeId": 10, "conditionTypeKey": "reps",       "displayOrder": 10, "displayable": True}
LAP_COND  = {"conditionTypeId": 1,  "conditionTypeKey": "lap.button", "displayOrder": 1,  "displayable": True}
ITER_COND = {"conditionTypeId": 7,  "conditionTypeKey": "iterations", "displayOrder": 7,  "displayable": False}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_REST     = {"stepTypeId": 5, "stepTypeKey": "rest",     "displayOrder": 5}
STEP_REPEAT   = {"stepTypeId": 6, "stepTypeKey": "repeat",   "displayOrder": 6}
NULL_STROKE = {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0}
NULL_EQUIP  = {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}
KG_UNIT     = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}


def make_step(order, child, cat, name, desc):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order, "stepType": STEP_INTERVAL, "childStepId": child,
        "description": desc, "endCondition": REPS_COND, "endConditionValue": 5.0,
        "preferredEndConditionUnit": None, "endConditionCompare": None,
        "targetType": NO_TARGET,
        "targetValueOne": None, "targetValueTwo": None, "targetValueUnit": None,
        "zoneNumber": None,
        "secondaryTargetType": None, "secondaryTargetValueOne": None,
        "secondaryTargetValueTwo": None, "secondaryTargetValueUnit": None,
        "secondaryZoneNumber": None, "endConditionZone": None,
        "strokeType": NULL_STROKE, "equipmentType": NULL_EQUIP,
        "category": cat, "exerciseName": name,
        "workoutProvider": None, "providerExerciseSourceId": None,
        "weightValue": -1.0, "weightUnit": KG_UNIT,
    }


def make_rest(order, child):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order, "stepType": STEP_REST, "childStepId": child,
        "description": "", "endCondition": LAP_COND, "endConditionValue": 0.0,
        "preferredEndConditionUnit": None, "endConditionCompare": None,
        "targetType": NO_TARGET,
        "targetValueOne": None, "targetValueTwo": None, "targetValueUnit": None,
        "zoneNumber": None,
        "secondaryTargetType": None, "secondaryTargetValueOne": None,
        "secondaryTargetValueTwo": None, "secondaryTargetValueUnit": None,
        "secondaryZoneNumber": None, "endConditionZone": None,
        "strokeType": NULL_STROKE, "equipmentType": NULL_EQUIP,
        "category": None, "exerciseName": None,
        "workoutProvider": None, "providerExerciseSourceId": None,
        "weightValue": -1.0, "weightUnit": KG_UNIT,
    }


def make_group(order, cid, inner):
    return {
        "type": "RepeatGroupDTO",
        "stepOrder": order, "stepType": STEP_REPEAT, "childStepId": cid,
        "numberOfIterations": 1, "workoutSteps": inner,
        "endCondition": ITER_COND, "endConditionValue": 1.0,
        "smartRepeat": False,
    }


# (category_sent, exerciseName_sent, status_label)
TEST_EXERCISES = [
    ("PUSH_UP",  "WIDE_PUSH_UP",    "unverified"),
    ("PUSH_UP",  "PIKE_PUSH_UP",    "unverified"),
    ("PLANK",    "SIDE_PLANK",      "unverified"),
    ("PULL_UP",  "PULL_UP",         "unverified"),
    ("PULL_UP",  "CHIN_UP",         "unverified"),
    ("SIT_UP",   "CRUNCH",          "unverified"),
    ("SIT_UP",   "SIT_UP",          "unverified"),
    ("SIT_UP",   "BICYCLE_CRUNCH",  "unverified"),
    ("ROW",      "FACE_PULL",       "unverified"),
    ("HIP_RAISE","BRIDGE",          "unverified"),
]

blocks = []
for i, (cat, name, _) in enumerate(TEST_EXERCISES):
    cid      = i + 1
    so_group = 1 + i * 3
    so_step  = so_group + 1
    so_rest  = so_group + 2
    blocks.append(make_group(so_group, cid, [
        make_step(so_step, cid, cat, name, f"TEST: {cat} | {name}"),
        make_rest(so_rest, cid),
    ]))

workout = {
    "workoutName": "VERIFY_EXERCISE_NAMES_DELETE_ME",
    "description": "Dummy workout to verify Garmin FIT SDK exercise name mapping. DELETE AFTER USE.",
    "sportType": STRENGTH,
    "estimatedDurationInSecs": 300,
    "workoutSegments": [{"segmentOrder": 1, "sportType": STRENGTH, "workoutSteps": blocks}],
}

result = client.client.upload_workout(workout)
workout_id = result.get("workoutId")
print(f"Uploaded dummy workout: {workout_id}\n")

# Fetch back and compare
fetched = client.client.get_workout_by_id(workout_id)
fetched_steps = []
for seg in fetched.get("workoutSegments", []):
    for blk in seg.get("workoutSteps", []):
        for inner in blk.get("workoutSteps", []):
            if inner.get("stepType", {}).get("stepTypeKey") == "interval":
                fetched_steps.append({
                    "category":     inner.get("category"),
                    "exerciseName": inner.get("exerciseName"),
                })

col = {"confirmed": "+ confirmed", "unverified": "? unverified", "likely_invalid": "X likely_invalid"}

print(f"{'SENT_CATEGORY':<28} {'SENT_NAME':<34} {'STATUS':<16} | {'GOT_CATEGORY':<28} {'GOT_NAME':<34} RESULT")
print("-" * 150)
for (cat_s, name_s, status), got in zip(TEST_EXERCISES, fetched_steps):
    cat_g  = got["category"]     or "None"
    name_g = got["exerciseName"] or "None"
    match  = "OK" if (cat_g == cat_s and name_g == name_s) else f"MISMATCH (got {cat_g} | {name_g})"
    print(f"{cat_s:<28} {name_s:<34} {col[status]:<16} | {cat_g:<28} {name_g:<34} {match}")

# Clean up
client.client.connectapi(f"/workout-service/workout/{workout_id}", method="DELETE")
print(f"\nDeleted dummy workout {workout_id}.")

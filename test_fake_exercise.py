#!/usr/bin/env python3
"""
Test: what happens when we upload a workout with invalid/invented exercise keys to Garmin?

Uploads a 3-exercise workout:
  1. Real key     — HIP_RAISE / BRIDGE (known good)
  2. Invented key — MADE_UP_CATEGORY / BULGARIAN_HIP_THRUST_PAUSE (plausible but fake)
  3. Nonsense key — ZZZZFAKE / NOTAREAL_EXERCISE (clearly garbage)

Then prints the workout ID so you can check how it looks in Garmin Connect + on the watch.
"""

import json
import sys
from pathlib import Path

from garminconnect import Garmin

TOKEN_DIR = Path.home() / ".config" / "garmin-connect-cli" / "tokens"

STRENGTH = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}

REPS_COND  = {"conditionTypeId": 10, "conditionTypeKey": "reps",        "displayOrder": 10, "displayable": True}
LAP_COND   = {"conditionTypeId": 1,  "conditionTypeKey": "lap.button",  "displayOrder": 1,  "displayable": True}
ITER_COND  = {"conditionTypeId": 7,  "conditionTypeKey": "iterations",  "displayOrder": 7,  "displayable": False}
NO_TARGET  = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
NULL_STROKE = {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0}
NULL_EQUIP  = {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}
KG_UNIT    = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}

STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_REST     = {"stepTypeId": 5, "stepTypeKey": "rest",     "displayOrder": 5}
STEP_REPEAT   = {"stepTypeId": 6, "stepTypeKey": "repeat",   "displayOrder": 6}


def ex_reps(order, child, reps, cat, name, desc=""):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": STEP_INTERVAL,
        "childStepId": child,
        "description": desc,
        "endCondition": REPS_COND,
        "endConditionValue": float(reps),
        "preferredEndConditionUnit": None,
        "endConditionCompare": None,
        "targetType": NO_TARGET,
        "targetValueOne": None, "targetValueTwo": None, "targetValueUnit": None,
        "zoneNumber": None,
        "secondaryTargetType": None,
        "secondaryTargetValueOne": None, "secondaryTargetValueTwo": None, "secondaryTargetValueUnit": None,
        "secondaryZoneNumber": None,
        "endConditionZone": None,
        "strokeType": NULL_STROKE,
        "equipmentType": NULL_EQUIP,
        "category": cat,
        "exerciseName": name,
        "workoutProvider": None,
        "providerExerciseSourceId": None,
        "weightValue": -1.0,
        "weightUnit": None,
    }


def rest_step(order, child):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": STEP_REST,
        "childStepId": child,
        "description": "",
        "endCondition": LAP_COND,
        "endConditionValue": 0.0,
        "preferredEndConditionUnit": None,
        "endConditionCompare": None,
        "targetType": NO_TARGET,
        "targetValueOne": None, "targetValueTwo": None, "targetValueUnit": None,
        "zoneNumber": None,
        "secondaryTargetType": None,
        "secondaryTargetValueOne": None, "secondaryTargetValueTwo": None, "secondaryTargetValueUnit": None,
        "secondaryZoneNumber": None,
        "endConditionZone": None,
        "strokeType": NULL_STROKE,
        "equipmentType": NULL_EQUIP,
        "category": None,
        "exerciseName": None,
        "workoutProvider": None,
        "providerExerciseSourceId": None,
        "weightValue": -1.0,
        "weightUnit": None,
    }


def rep_group(order, child_id, iters, inner_steps):
    return {
        "type": "RepeatGroupDTO",
        "stepOrder": order,
        "stepType": STEP_REPEAT,
        "childStepId": child_id,
        "numberOfIterations": iters,
        "workoutSteps": inner_steps,
        "endCondition": ITER_COND,
        "endConditionValue": float(iters),
        "smartRepeat": False,
    }


def build_test_workout():
    steps = []

    # 1. Real exercise — should display correctly
    steps.append(rep_group(1, 1, 3, [
        ex_reps(2, 1, 12, "HIP_RAISE", "BRIDGE",
                "REAL KEY: HIP_RAISE/BRIDGE — should show as Glute Bridge"),
        rest_step(3, 1),
    ]))

    # 2. Plausible but invented category — close to real but not in catalog
    steps.append(rep_group(4, 2, 3, [
        ex_reps(5, 2, 10, "MADE_UP_CATEGORY", "BULGARIAN_HIP_THRUST_PAUSE",
                "INVENTED CATEGORY: what does Garmin do with this?"),
        rest_step(6, 2),
    ]))

    # 3. Pure garbage keys
    steps.append(rep_group(7, 3, 3, [
        ex_reps(8, 3, 8, "ZZZZFAKE", "NOTAREAL_EXERCISE",
                "GARBAGE KEY: clearly fake — accepted or rejected?"),
        rest_step(9, 3),
    ]))

    return {
        "workoutName": "TEST — Fake Exercise Keys",
        "description": "Testing how Garmin handles invalid exercise keys. Delete after checking.",
        "sportType": STRENGTH,
        "estimatedDurationInSecs": 900,
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": STRENGTH, "workoutSteps": steps}
        ],
    }


def main():
    print("Connecting to Garmin Connect...")
    client = Garmin()
    client.login(str(TOKEN_DIR))
    print("Connected.\n")

    w = build_test_workout()
    print("Uploading test workout with 3 exercises:")
    print("  1. REAL      — HIP_RAISE / BRIDGE")
    print("  2. INVENTED  — MADE_UP_CATEGORY / BULGARIAN_HIP_THRUST_PAUSE")
    print("  3. GARBAGE   — ZZZZFAKE / NOTAREAL_EXERCISE")
    print()

    try:
        result = client.upload_workout(w)
        wid = result.get("workoutId", "?")
        print(f"[UPLOAD OK] workoutId = {wid}")
        print()
        print("Check Garmin Connect (web or app) — open the workout library and find")
        print(f"'TEST — Fake Exercise Keys' (id={wid}).")
        print("See how each exercise displays: name shown, or blank, or error.")
        print()
        print(f"To delete it after checking:")
        print(f"  python -c \"")
        print(f"  from garminconnect import Garmin; from pathlib import Path")
        print(f"  g = Garmin(); g.login(str(Path.home()/'.config/garmin-connect-cli/tokens'))")
        print(f"  g.delete_workout({wid}); print('Deleted')\"")
    except Exception as e:
        print(f"[UPLOAD FAILED] {type(e).__name__}: {e}")
        print()
        print("Garmin rejected the upload — probably validates keys server-side.")
        if hasattr(e, 'response') and e.response is not None:
            print(f"HTTP status: {e.response.status_code}")
            print(f"Response: {e.response.text[:500]}")


if __name__ == "__main__":
    main()

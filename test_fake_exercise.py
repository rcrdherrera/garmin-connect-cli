#!/usr/bin/env python3
"""
Probes:
  1. Fetch Garmin's exercise catalog (valid category + exercise name keys)
  2. Test uploading with one invalid key to confirm 400 behavior
  3. Test uploading with all-real keys to confirm success path

Run on the Ubuntu server after git pull:
  uv run python test_fake_exercise.py
"""

import json
import sys
from pathlib import Path

from garminconnect import Garmin

TOKEN_DIR = Path.home() / ".config" / "garmin-connect-cli" / "tokens"

STRENGTH     = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
REPS_COND    = {"conditionTypeId": 10, "conditionTypeKey": "reps",       "displayOrder": 10, "displayable": True}
LAP_COND     = {"conditionTypeId": 1,  "conditionTypeKey": "lap.button", "displayOrder": 1,  "displayable": True}
ITER_COND    = {"conditionTypeId": 7,  "conditionTypeKey": "iterations", "displayOrder": 7,  "displayable": False}
NO_TARGET    = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
NULL_STROKE  = {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0}
NULL_EQUIP   = {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}
STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_REST    = {"stepTypeId": 5, "stepTypeKey": "rest",     "displayOrder": 5}
STEP_REPEAT  = {"stepTypeId": 6, "stepTypeKey": "repeat",   "displayOrder": 6}


def ex_reps(order, child, reps, cat, name, desc=""):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order, "stepType": STEP_INTERVAL, "childStepId": child,
        "description": desc, "endCondition": REPS_COND, "endConditionValue": float(reps),
        "preferredEndConditionUnit": None, "endConditionCompare": None,
        "targetType": NO_TARGET,
        "targetValueOne": None, "targetValueTwo": None, "targetValueUnit": None,
        "zoneNumber": None, "secondaryTargetType": None,
        "secondaryTargetValueOne": None, "secondaryTargetValueTwo": None,
        "secondaryTargetValueUnit": None, "secondaryZoneNumber": None,
        "endConditionZone": None, "strokeType": NULL_STROKE, "equipmentType": NULL_EQUIP,
        "category": cat, "exerciseName": name,
        "workoutProvider": None, "providerExerciseSourceId": None,
        "weightValue": -1.0, "weightUnit": None,
    }


def rest_step(order, child):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order, "stepType": STEP_REST, "childStepId": child,
        "description": "", "endCondition": LAP_COND, "endConditionValue": 0.0,
        "preferredEndConditionUnit": None, "endConditionCompare": None,
        "targetType": NO_TARGET,
        "targetValueOne": None, "targetValueTwo": None, "targetValueUnit": None,
        "zoneNumber": None, "secondaryTargetType": None,
        "secondaryTargetValueOne": None, "secondaryTargetValueTwo": None,
        "secondaryTargetValueUnit": None, "secondaryZoneNumber": None,
        "endConditionZone": None, "strokeType": NULL_STROKE, "equipmentType": NULL_EQUIP,
        "category": None, "exerciseName": None,
        "workoutProvider": None, "providerExerciseSourceId": None,
        "weightValue": -1.0, "weightUnit": None,
    }


def rep_group(order, child_id, iters, inner_steps):
    return {
        "type": "RepeatGroupDTO", "stepOrder": order, "stepType": STEP_REPEAT,
        "childStepId": child_id, "numberOfIterations": iters,
        "workoutSteps": inner_steps, "endCondition": ITER_COND,
        "endConditionValue": float(iters), "smartRepeat": False,
    }


def make_workout(name, steps):
    return {
        "workoutName": name,
        "description": "Test workout — delete after checking.",
        "sportType": STRENGTH,
        "estimatedDurationInSecs": 600,
        "workoutSegments": [{"segmentOrder": 1, "sportType": STRENGTH, "workoutSteps": steps}],
    }


def try_upload(client, name, steps):
    try:
        result = client.upload_workout(make_workout(name, steps))
        wid = result.get("workoutId", "?")
        print(f"  [OK] workoutId={wid}")
        return wid
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {str(e)[:200]}")
        return None


def fetch_catalog(client):
    """Try known Garmin exercise catalog endpoints."""
    endpoints = [
        "/workout-service/exercise/types",
        "/workout-service/workout/exercise/types",
        "/workout-service/exercise/categories",
    ]
    for ep in endpoints:
        try:
            resp = client.garth.get("connectapi", ep, api=True)
            data = resp.json()
            print(f"  [OK] {ep} → {type(data).__name__}, len={len(data) if isinstance(data, list) else 'dict'}")
            return ep, data
        except Exception as e:
            print(f"  [FAIL] {ep}: {str(e)[:120]}")
    return None, None


def main():
    print("Connecting to Garmin Connect...")
    client = Garmin()
    client.login(str(TOKEN_DIR))
    print("Connected.\n")

    # ── 1. Fetch exercise catalog ─────────────────────────────────────────────
    print("━━━ 1. FETCHING EXERCISE CATALOG ━━━")
    ep, catalog_data = fetch_catalog(client)

    if catalog_data:
        # Save full catalog to file for inspection
        out = Path("garmin_exercise_catalog.json")
        out.write_text(json.dumps(catalog_data, indent=2))
        print(f"\n  Full catalog saved to: {out.resolve()}")

        # Show structure of first 2 entries
        print("\n  Sample (first 2 entries):")
        sample = catalog_data[:2] if isinstance(catalog_data, list) else list(catalog_data.items())[:2]
        print(json.dumps(sample, indent=4))
    else:
        print("  Could not fetch catalog from any endpoint.")

    # ── 2. Upload with one fake key to confirm rejection ─────────────────────
    print("\n━━━ 2. SINGLE FAKE KEY (should fail) ━━━")
    try_upload(client, "TEST — Single Fake Key", [
        rep_group(1, 1, 2, [
            ex_reps(2, 1, 10, "ZZZZFAKE", "NOTAREAL_EXERCISE", "fake key test"),
            rest_step(3, 1),
        ])
    ])

    # ── 3. Upload with all-real keys (should succeed) ────────────────────────
    print("\n━━━ 3. ALL REAL KEYS (should succeed) ━━━")
    wid = try_upload(client, "TEST — Real Keys Only", [
        rep_group(1, 1, 3, [
            ex_reps(2, 1, 12, "HIP_RAISE", "BRIDGE", "Glute bridge — real key"),
            rest_step(3, 1),
        ])
    ])
    if wid:
        print(f"\n  Check Garmin app → workout library → 'TEST — Real Keys Only'")
        print(f"  Then delete: the workout ID is {wid}")

    print("\nDone.")


if __name__ == "__main__":
    main()

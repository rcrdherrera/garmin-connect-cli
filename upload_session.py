import sys
sys.path.insert(0, r"C:\garmin-connect-cli\src")
from garmin_connect_cli.client import GarminClient
from garmin_connect_cli.config import Config

config = Config.load()
client = GarminClient(config)
client.ensure_authenticated()

# --- Primitives ---
STRENGTH  = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
REPS_COND = {"conditionTypeId": 10, "conditionTypeKey": "reps",       "displayOrder": 10, "displayable": True}
TIME_COND = {"conditionTypeId": 2,  "conditionTypeKey": "time",       "displayOrder": 2,  "displayable": True}
LAP_COND  = {"conditionTypeId": 1,  "conditionTypeKey": "lap.button", "displayOrder": 1,  "displayable": True}
ITER_COND = {"conditionTypeId": 7,  "conditionTypeKey": "iterations", "displayOrder": 7,  "displayable": False}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
STEP_WARMUP   = {"stepTypeId": 1, "stepTypeKey": "warmup",   "displayOrder": 1}
STEP_COOLDOWN = {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2}
STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_REST     = {"stepTypeId": 5, "stepTypeKey": "rest",     "displayOrder": 5}
STEP_REPEAT   = {"stepTypeId": 6, "stepTypeKey": "repeat",   "displayOrder": 6}
NULL_STROKE   = {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0}
NULL_EQUIP    = {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}
KG_UNIT       = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}


def _base_step(order, child, step_type, end_cond, end_val, target, desc, cat, name, weight):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order, "stepType": step_type, "childStepId": child,
        "description": desc, "endCondition": end_cond, "endConditionValue": float(end_val),
        "preferredEndConditionUnit": None, "endConditionCompare": None,
        "targetType": target,
        "targetValueOne": None, "targetValueTwo": None, "targetValueUnit": None,
        "zoneNumber": None,
        "secondaryTargetType": None, "secondaryTargetValueOne": None,
        "secondaryTargetValueTwo": None, "secondaryTargetValueUnit": None,
        "secondaryZoneNumber": None, "endConditionZone": None,
        "strokeType": NULL_STROKE, "equipmentType": NULL_EQUIP,
        "category": cat, "exerciseName": name,
        "workoutProvider": None, "providerExerciseSourceId": None,
        "weightValue": weight, "weightUnit": KG_UNIT if weight is not None else None,
    }

def ex_reps(order, child, reps, cat, name, desc=""):
    return _base_step(order, child, STEP_INTERVAL, REPS_COND, reps, NO_TARGET, desc, cat, name, -1.0)

def ex_reps_w(order, child, reps, cat, name, weight_kg, desc=""):
    return _base_step(order, child, STEP_INTERVAL, REPS_COND, reps, NO_TARGET, desc, cat, name, weight_kg)

def ex_time(order, child, secs, cat, name, desc=""):
    return _base_step(order, child, STEP_INTERVAL, TIME_COND, secs, NO_TARGET, desc, cat, name, -1.0)

def rest(order, child):
    return _base_step(order, child, STEP_REST, LAP_COND, 0.0, NO_TARGET, "", None, None, -1.0)

def rep_group(order, child_id, iters, inner_steps):
    return {
        "type": "RepeatGroupDTO",
        "stepOrder": order, "stepType": STEP_REPEAT, "childStepId": child_id,
        "numberOfIterations": iters, "workoutSteps": inner_steps,
        "endCondition": ITER_COND, "endConditionValue": float(iters),
        "smartRepeat": False,
    }

def workout(name, desc, sport, steps, duration_secs):
    return {
        "workoutName": name, "description": desc, "sportType": sport,
        "estimatedDurationInSecs": duration_secs,
        "workoutSegments": [{"segmentOrder": 1, "sportType": sport, "workoutSteps": steps}],
    }

# --- Steps ---
# stepOrder globally sequential; inner steps of each rep_group share the group's child_id

warmup = _base_step(1, None, STEP_WARMUP, TIME_COND, 300.0, NO_TARGET,
    "Movilidad articular: rotaciones de cadera, hombros y tobillos. 5 min.", None, None, None)

# Block 1 — Upper Push (child_id=1, 3 sets)
b1_pushup  = ex_reps(3, 1, 12, "PUSH_UP", "PUSH_UP",         "Core apretado, pecho hasta el suelo")
b1_diamond = ex_reps(4, 1, 10, "PUSH_UP", "DIAMOND_PUSH_UP", "Manos en triángulo, énfasis tríceps")
b1_rest    = rest(5, 1)
block1     = rep_group(2, 1, 3, [b1_pushup, b1_diamond, b1_rest])

# Block 2 — Upper Pull (child_id=2, 3 sets)
b2_row_l = ex_reps_w(7, 2, 12, None, None, 10.0,
    "Remo a 1 brazo IZQUIERDO, DB 10kg apoyado en banca. Codo hacia arriba.")
b2_row_r = ex_reps_w(8, 2, 12, None, None, 10.0,
    "Remo a 1 brazo DERECHO, DB 10kg apoyado en banca. Codo hacia arriba.")
b2_face  = ex_reps(9, 2, 15, None, None,
    "Face pull con banda: codos a altura de hombros, rotación externa al final")
b2_rest  = rest(10, 2)
block2   = rep_group(6, 2, 3, [b2_row_l, b2_row_r, b2_face, b2_rest])

# Block 3 — Core (child_id=3, 3 sets)
b3_plank   = ex_time(12, 3, 40, "PLANK", "PLANK",
    "Core firme, pelvis neutra, sin hundir caderas")
b3_bicycle = ex_reps(13, 3, 20, "SIT_UP", "BICYCLE_CRUNCH",
    "Rotación controlada, codo toca rodilla opuesta")
b3_rest    = rest(14, 3)
block3     = rep_group(11, 3, 3, [b3_plank, b3_bicycle, b3_rest])

# Block 4 — Hip/Glute single-leg (child_id=4, 3 sets)
b4_slr_l = ex_reps(16, 4, 12, "HIP_RAISE", "SINGLE_LEG_HIP_RAISE",
    "PIERNA IZQ elevada. Sube 1s — mantén 1s — baja 2s. Glúteo activo.")
b4_slr_r = ex_reps(17, 4, 12, "HIP_RAISE", "SINGLE_LEG_HIP_RAISE",
    "PIERNA DER elevada. Sube 1s — mantén 1s — baja 2s. Glúteo activo.")
b4_rest  = rest(18, 4)
block4   = rep_group(15, 4, 3, [b4_slr_l, b4_slr_r, b4_rest])

# Block 5 — Eccentric Calf Raises / posterior PTT (child_id=5, 3 sets)
b5_calf = ex_reps(20, 5, 15, "CALF_RAISE", "STANDING_CALF_RAISE",
    "Sube 1s — BAJA 3s MUY LENTO. Carga excéntrica gastrocnemio+sóleo. PTT.")
b5_rest = rest(21, 5)
block5  = rep_group(19, 5, 3, [b5_calf, b5_rest])

# Block 6 — Tibialis Anterior Raises / anterior PTT (child_id=6, 3 sets)
b6_tib  = ex_reps(23, 6, 15, None, None,
    "Barra tibial en incline bench: dorsiflexión SUBE 1s — BAJA 3s. Excéntrico tibial anterior. PTT.")
b6_rest = rest(24, 6)
block6  = rep_group(22, 6, 3, [b6_tib, b6_rest])

cooldown = _base_step(25, None, STEP_COOLDOWN, TIME_COND, 300.0, NO_TARGET,
    "Estira: pantorrilla en pared (1min c/lado), tibial anterior sentado, pecho en marco, espalda.", None, None, None)

all_steps = [warmup, block1, block2, block3, block4, block5, block6, cooldown]

w = workout(
    "Full Body — Upper + PTT Calf",
    "Fase 3 Sem 7 | Upper push/pull + core + glúteo + calf excéntrico posterior+anterior. Lun 29 Jun.",
    STRENGTH,
    all_steps,
    3900,
)

import json
print(json.dumps(w, indent=2, ensure_ascii=False))

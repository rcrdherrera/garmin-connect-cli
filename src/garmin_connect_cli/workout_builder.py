"""Canonical building blocks for Garmin structured workouts.

Single source of truth for the step/segment primitives previously duplicated
(with drift) across create_workouts.py, .claude/commands/coach.md, and
various per-session scratch scripts. Import this instead of re-pasting the
primitives block.

Usage sketch:

    from garmin_connect_cli.workout_builder import (
        STRENGTH, STEP_WARMUP, STEP_COOLDOWN,
        ex_reps, ex_reps_w, ex_time, rest, run_seg, workout,
        StepSequencer, validate_exercise,
    )

    seq = StepSequencer()
    steps = [run_seg(seq.next_order(), STEP_WARMUP, 300, "Dynamic warmup")]

    steps.append(seq.block(3, lambda o, c: [
        ex_reps(o(), c, 12, "PUSH_UP", "PUSH_UP", "Standard push-up"),
        rest(o(), c),
    ]))

    for cat, name in [("PUSH_UP", "PUSH_UP")]:
        warnings = validate_exercise(cat, name)
        if warnings:
            print(warnings)

    w = workout("My Workout", "desc", STRENGTH, steps, duration_secs=1800)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_EXERCISES_PATH = _DATA_DIR / "garmin_exercises_equipment.json"
_EQUIPMENT_PATH = _DATA_DIR / "my_equipment.json"

# ─── Sport types ──────────────────────────────────────────────────────────────
STRENGTH = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
RUNNING = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}

# ─── End conditions ───────────────────────────────────────────────────────────
REPS_COND = {
    "conditionTypeId": 10,
    "conditionTypeKey": "reps",
    "displayOrder": 10,
    "displayable": True,
}
TIME_COND = {
    "conditionTypeId": 2,
    "conditionTypeKey": "time",
    "displayOrder": 2,
    "displayable": True,
}
LAP_COND = {
    "conditionTypeId": 1,
    "conditionTypeKey": "lap.button",
    "displayOrder": 1,
    "displayable": True,
}
ITER_COND = {
    "conditionTypeId": 7,
    "conditionTypeKey": "iterations",
    "displayOrder": 7,
    "displayable": False,
}

# ─── Targets ──────────────────────────────────────────────────────────────────
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}

# ─── Step types ───────────────────────────────────────────────────────────────
STEP_WARMUP = {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1}
STEP_COOLDOWN = {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2}
STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_RECOVERY = {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4}
STEP_REST = {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5}
STEP_REPEAT = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}

NULL_STROKE = {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0}
NULL_EQUIP = {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}
# NOTE: weightValue is passed straight through in kg (NOT grams). The `factor: 1000.0`
# below looked like it might imply a gram-based base unit, but this was checked against
# the live Garmin Connect app (2026-07-06): a workout uploaded with weightValue=16.0
# displayed as "16kg" on-device, not 0.016kg. factor is descriptive metadata on the
# kilogram unit definition, not a divisor applied to weightValue. Do not "fix" this again.
KG_UNIT = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}


def _base_step(order, child, step_type, end_cond, end_val, target, desc, cat, name, weight):
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": step_type,
        "childStepId": child,
        "description": desc,
        "endCondition": end_cond,
        "endConditionValue": float(end_val),
        "preferredEndConditionUnit": None,
        "endConditionCompare": None,
        "targetType": target,
        "targetValueOne": None,
        "targetValueTwo": None,
        "targetValueUnit": None,
        "zoneNumber": None,
        "secondaryTargetType": None,
        "secondaryTargetValueOne": None,
        "secondaryTargetValueTwo": None,
        "secondaryTargetValueUnit": None,
        "secondaryZoneNumber": None,
        "endConditionZone": None,
        "strokeType": NULL_STROKE,
        "equipmentType": NULL_EQUIP,
        "category": cat,
        "exerciseName": name,
        "workoutProvider": None,
        "providerExerciseSourceId": None,
        "weightValue": weight,
        "weightUnit": KG_UNIT if weight is not None else None,
    }


def ex_reps(order, child, reps, cat, name, desc=""):
    """Bodyweight strength exercise, rep-counted."""
    return _base_step(
        order, child, STEP_INTERVAL, REPS_COND, reps, NO_TARGET, desc, cat, name, -1.0
    )


def ex_reps_w(order, child, reps, cat, name, weight_kg, desc=""):
    """Weighted strength exercise, rep-counted.

    weight_kg = total load in kg (e.g. 20.0 for 2x10kg DBs).
    """
    return _base_step(
        order, child, STEP_INTERVAL, REPS_COND, reps, NO_TARGET, desc, cat, name, weight_kg
    )


def ex_time(order, child, secs, cat, name, desc=""):
    """Time-based exercise (plank, hold)."""
    return _base_step(
        order, child, STEP_INTERVAL, TIME_COND, secs, NO_TARGET, desc, cat, name, -1.0
    )


def rest(order, child):
    """Rest between sets - press lap to continue."""
    return _base_step(order, child, STEP_REST, LAP_COND, 0.0, NO_TARGET, "", None, None, -1.0)


def run_seg(order, step_type, secs, desc="", child=None):
    """Running segment (warmup / interval / recovery / cooldown), also used for
    non-exercise strength-workout segments like warmup/cooldown (weight=None)."""
    return _base_step(order, child, step_type, TIME_COND, secs, NO_TARGET, desc, None, None, None)


def rep_group(order, child_id, iters, inner_steps):
    """N sets of the inner steps. child_id increments per exercise block."""
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


def workout(name, desc, sport, steps, duration_secs):
    return {
        "workoutName": name,
        "description": desc,
        "sportType": sport,
        "estimatedDurationInSecs": duration_secs,
        "workoutSegments": [{"segmentOrder": 1, "sportType": sport, "workoutSteps": steps}],
    }


class StepSequencer:
    """Tracks global stepOrder and per-block childStepId counters so callers
    never hand-increment order/child again (the `next_o()`/`next_g()` closure
    pattern every prior script rolled by hand).

    stepOrder is globally sequential across the entire workout. childStepId
    increments once per exercise block (all steps inside one rep_group share
    the same child id); standalone steps (warmup/cooldown) use child=None.
    """

    def __init__(self):
        self._order = 1
        self._child = 0

    def next_order(self) -> int:
        o = self._order
        self._order += 1
        return o

    def standalone(self, builder_fn: Callable[[int], dict]) -> dict:
        """Build one standalone step (e.g. warmup/cooldown) at the next order, child=None."""
        return builder_fn(self.next_order())

    def block(self, sets: int, steps_fn: Callable[[Callable[[], int], int], list]) -> dict:
        """Wrap steps_fn's output in one rep_group.

        steps_fn receives (o, child_id) where o() allocates the next stepOrder
        on each call and child_id is this block's childStepId - use both when
        building each inner ex_reps/ex_time/rest call.
        """
        self._child += 1
        child_id = self._child
        group_order = self.next_order()
        inner = steps_fn(self.next_order, child_id)
        return rep_group(group_order, child_id, sets, inner)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _catalog() -> list[dict]:
    """Garmin's own exercise catalog (data/garmin_exercises_equipment.json), cached.

    Static repo data - safe to cache for the lifetime of the process (a long-running
    server included; changes are picked up on next restart/deploy same as any other
    code change).
    """
    return _load_json(_EXERCISES_PATH)


@lru_cache(maxsize=1)
def _equipment_lookup() -> dict[tuple[str, str], list[str]]:
    """(category, exerciseKey) -> equipmentKeys, built once from _catalog()."""
    return {
        (cat_obj["exerciseCategoryKey"], ex["exerciseKey"]): ex.get("equipmentKeys", [])
        for cat_obj in _catalog()
        for ex in cat_obj.get("exercisesInCategory", [])
    }


@lru_cache(maxsize=1)
def _owned_equipment() -> set[str]:
    return set(_load_json(_EQUIPMENT_PATH)["owned"])


def _exercise_equipment(category: str, name: str) -> list[str] | None:
    """Look up equipmentKeys for (category, name) in the Garmin exercise catalog.
    Returns None if the (category, name) pair doesn't exist in the catalog."""
    return _equipment_lookup().get((category, name))


def build_curated_catalog(skip_categories: frozenset[str] = frozenset()) -> dict[str, list[str]]:
    """category -> sorted exercise names whose full equipment set is owned.

    Used to build a much smaller, equipment-aware exercise catalog for prompts
    (e.g. server.py's _coach_system()) instead of dumping every exercise Garmin
    knows about regardless of whether the athlete can actually perform it.
    """
    owned = _owned_equipment()
    result: dict[str, list[str]] = {}
    for cat_obj in _catalog():
        cat = cat_obj["exerciseCategoryKey"]
        if cat in skip_categories:
            continue
        names = sorted(
            ex["exerciseKey"]
            for ex in cat_obj.get("exercisesInCategory", [])
            if set(ex.get("equipmentKeys", [])) <= owned
        )
        if names:
            result[cat] = names
    return result


def validate_exercise(category: str | None, name: str | None) -> list[str]:
    """Validate a (category, name) pair before using it in a workout step.

    Returns an empty list if valid: the pair exists in Garmin's own exercise
    catalog (data/garmin_exercises_equipment.json) AND every equipment it
    requires is in data/my_equipment.json's owned list.

    Returns a list of human-readable warnings otherwise - the caller should
    fall back to category=None, name=None (keeping a descriptive `desc`)
    when any warning is returned, since Garmin silently drops exerciseName
    values it doesn't recognize rather than erroring.

    Note: an equipment-mismatch warning is a signal, not always an absolute
    block - Garmin's equipmentKeys reflect its own suggested/typical
    equipment for a named variant, which sometimes differs from a legitimate
    real-world substitute (e.g. ROW/FACE_PULL is tagged CABLE_MACHINE, but a
    resistance band is a standard substitute for that exact movement). Use
    judgment before falling back; a not-in-catalog warning has no such
    ambiguity and should always trigger the fallback.
    """
    if category is None and name is None:
        return []
    if category is None or name is None:
        return [f"category={category!r} and name={name!r} must both be set or both be None"]

    equipment_needed = _exercise_equipment(category, name)
    if equipment_needed is None:
        return [
            f"{category}/{name} is not in Garmin's exercise catalog "
            f"(data/garmin_exercises_equipment.json) - Garmin will silently drop the "
            f"exerciseName and keep the category only. "
            f"Use category=None, name=None with a descriptive desc instead."
        ]

    owned = _owned_equipment()
    missing = [eq for eq in equipment_needed if eq not in owned]
    if missing:
        return [
            f"{category}/{name} requires {missing} which is not in the home equipment "
            f"inventory (data/my_equipment.json owned={sorted(owned)}). "
            f"Use category=None, name=None with a descriptive desc instead."
        ]
    return []

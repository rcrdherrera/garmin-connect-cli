#!/usr/bin/env python3
"""
Science-based training workouts for Ricardo — Phase 1: Return-to-Run (May 2026)

Coach rationale:
  Running:
    - Walk-run 2:1 ratio, HR<155: safe PTT loading while rebuilding aerobic base
    - Z2 easy run: polarized model, ~80% volume below LT1 (162 bpm)
    - Cadence cue in description: target 168-172 spm (from 153 baseline, +10% per evidence)

  Strength:
    - Hip/glute strength: reduces excessive pronation loading on PTT (Semciw et al.)
    - Eccentric calf work: rebuilds tendon collagen (modified Alfredson protocol)
    - Single-leg stability: key biomechanical prerequisite for return to running
    - Upper body/core: running economy +2-4% over 12-16 weeks (Berryman 2018 meta-analysis)
    - Posterior chain: hip hinge patterns reduce proximal loading on distal tendons
"""

import json
import sys
from pathlib import Path

from garminconnect import Garmin

TOKEN_DIR = Path.home() / ".config" / "garmin-connect-cli" / "tokens"


# ─── Sport types ─────────────────────────────────────────────────────────────

STRENGTH = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
RUNNING = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}

# ─── End conditions ──────────────────────────────────────────────────────────

REPS_COND = {
    "conditionTypeId": 10, "conditionTypeKey": "reps",
    "displayOrder": 10, "displayable": True,
}
TIME_COND = {
    "conditionTypeId": 2, "conditionTypeKey": "time",
    "displayOrder": 2, "displayable": True,
}
LAP_COND = {
    "conditionTypeId": 1, "conditionTypeKey": "lap.button",
    "displayOrder": 1, "displayable": True,
}
ITER_COND = {
    "conditionTypeId": 7, "conditionTypeKey": "iterations",
    "displayOrder": 7, "displayable": False,
}

# ─── Targets ─────────────────────────────────────────────────────────────────

NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}

# ─── Misc ────────────────────────────────────────────────────────────────────

NULL_STROKE = {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0}
NULL_EQUIP = {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}
KG_UNIT = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}

STEP_WARMUP = {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1}
STEP_COOLDOWN = {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2}
STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_RECOVERY = {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4}
STEP_REST = {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5}
STEP_REPEAT = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}


# ─── Step builders ───────────────────────────────────────────────────────────

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
    return _base_step(order, child, STEP_INTERVAL, REPS_COND, reps,
                      NO_TARGET, desc, cat, name, -1.0)


def ex_time(order, child, secs, cat, name, desc=""):
    """Bodyweight strength exercise, time-based (plank, hold)."""
    return _base_step(order, child, STEP_INTERVAL, TIME_COND, secs,
                      NO_TARGET, desc, cat, name, -1.0)


def rest(order, child):
    """Rest between sets — press lap to continue."""
    return _base_step(order, child, STEP_REST, LAP_COND, 0.0,
                      NO_TARGET, "", None, None, -1.0)


def run_seg(order, step_type, secs, desc="", child=None):
    """Running workout segment (warmup / interval / recovery / cooldown)."""
    return _base_step(order, child, step_type, TIME_COND, secs,
                      NO_TARGET, desc, None, None, None)


def rep_group(order, child_id, iters, inner_steps):
    """Repeat group: N sets of the inner steps."""
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
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": sport, "workoutSteps": steps}
        ],
    }


# ─── Workout definitions ─────────────────────────────────────────────────────

def walk_run_protocol():
    """
    Walk-Run Return Protocol — 25min
    Structure: 5min warm-up walk → 5x(2min run + 1min walk) → 5min cool-down walk
    HR target: <155 bpm (bottom of Z2); cadence cue: 168 spm
    Science: Gradual tendon loading; 2:1 walk-run proven safe for tendon rehab return.
    """
    steps = [
        run_seg(1, STEP_WARMUP, 300, "Walk warm-up. Easy pace, loosen up."),
        rep_group(2, 1, 5, [
            run_seg(3, STEP_INTERVAL, 120,
                    "RUN — HR target <155. Cadence 168 spm. Light, quick steps.", child=1),
            run_seg(4, STEP_RECOVERY, 60,
                    "WALK recovery. Breathe, let HR drop.", child=1),
        ]),
        run_seg(5, STEP_COOLDOWN, 300, "Walk cool-down. Easy pace."),
    ]
    return workout(
        "Return Protocol: Walk-Run",
        "PTT return protocol. 5x (2min run / 1min walk). HR<155 bpm. "
        "Cadence target 168 spm — use metronome. No pain = green light to progress.",
        RUNNING, steps, 1500,
    )


def z2_easy_run():
    """
    Z2 Base Builder — 30min
    Structure: 5min walk → 20min easy run → 5min walk
    HR target: 145-162 bpm (Z2, below LT1); cadence: 168-172 spm
    Science: Polarized model — 80% volume below LT1 rebuilds aerobic base.
    """
    steps = [
        run_seg(1, STEP_WARMUP, 300, "Walk warm-up. Activate glutes before running."),
        run_seg(2, STEP_INTERVAL, 1200,
                "Easy run. HR 145-162 (Z2). Cadence 168-172 spm. Conversational pace. "
                "If PTT feels anything, drop to walk immediately."),
        run_seg(3, STEP_COOLDOWN, 300, "Walk cool-down. Calf stretch after."),
    ]
    return workout(
        "Z2 Base Builder — Easy Run",
        "Aerobic base session. HR 145-162 (Z2, below LT1 162 bpm). "
        "Cadence 168-172 spm. 20min continuous — stop if any PTT discomfort.",
        RUNNING, steps, 1800,
    )


def lower_body_hip_glute():
    """
    Lower Body: Hip & Glute — 45min
    Focus: PTT rehab via proximal strength (hip abductors/extensors reduce pronation loading)
    Science: Hip strength deficit → excessive femoral IR → pronation → PTT overload (Semciw et al.)
             Eccentric calf loading rebuilds tendon collagen at low load (modified Alfredson).
    Exercises:
      1. Glute Bridge (HIP_RAISE/BRIDGE) 4x15 — glute max activation, key PTT offloader
      2. Single-Leg Hip Raise (HIP_RAISE/SINGLE_LEG_HIP_RAISE) 3x12 each — unilateral glute
      3. Split Squat (SQUAT/SPLIT_SQUAT) 3x10 each — hip/quad, sport-specific single-leg
      4. Reverse Lunge (LUNGE/REVERSE_LUNGE) 3x10 each — glute dominant, knee-safe
      5. Calf Raise (CALF_RAISE/STANDING_CALF_RAISE) 3x15 slow eccentric — tendon rehab
    """
    o = 1  # stepOrder counter

    def next_o():
        nonlocal o
        v = o
        o += 1
        return v

    g = 1  # group/childStepId counter

    def next_g():
        nonlocal g
        v = g
        g += 1
        return v

    steps = []

    # 1. Glute Bridge 4x15
    gid = next_g()
    rg_o = next_o()
    steps.append(rep_group(rg_o, gid, 4, [
        ex_reps(next_o(), gid, 15, "HIP_RAISE", "BRIDGE",
                "Glute bridge. Squeeze at top 1sec. Pelvis neutral."),
        rest(next_o(), gid),
    ]))

    # 2. Single-Leg Hip Raise 3x12
    gid = next_g()
    rg_o = next_o()
    steps.append(rep_group(rg_o, gid, 3, [
        ex_reps(next_o(), gid, 12, "HIP_RAISE", "SINGLE_LEG_HIP_RAISE",
                "Single-leg glute bridge. 12 each side. Keep hips level."),
        rest(next_o(), gid),
    ]))

    # 3. Split Squat 3x10 each
    gid = next_g()
    rg_o = next_o()
    steps.append(rep_group(rg_o, gid, 3, [
        ex_reps(next_o(), gid, 10, "SQUAT", "SPLIT_SQUAT",
                "Split squat. 10 each leg. Front knee tracks toe. Upright torso."),
        rest(next_o(), gid),
    ]))

    # 4. Reverse Lunge 3x10 each
    gid = next_g()
    rg_o = next_o()
    steps.append(rep_group(rg_o, gid, 3, [
        ex_reps(next_o(), gid, 10, "LUNGE", "REVERSE_LUNGE",
                "Reverse lunge. 10 each leg. Step back, lower knee to floor."),
        rest(next_o(), gid),
    ]))

    # 5. Calf Raise 3x15 slow eccentric
    gid = next_g()
    rg_o = next_o()
    steps.append(rep_group(rg_o, gid, 3, [
        ex_reps(next_o(), gid, 15, "CALF_RAISE", "STANDING_CALF_RAISE",
                "Calf raise. Rise 1sec, LOWER 3sec (eccentric focus). Tendon rehab."),
        rest(next_o(), gid),
    ]))

    return workout(
        "Lower Body: Hip & Glute — PTT Focus",
        "PTT rehab strength. Glute/hip work offloads the posterior tibial tendon. "
        "Eccentric calf lowers (3sec down) rebuild tendon collagen. 3-4 sets each. "
        "Rest 90-120sec between sets (press lap). STOP if any PTT pain.",
        STRENGTH, steps, 2700,
    )


def upper_body_core():
    """
    Upper Body + Core: Running Economy — 40min
    Focus: Trunk/arm strength for running economy; core for load transfer
    Science: Concurrent strength training improves running economy +2-4% (Berryman 2018).
             Trunk endurance and anti-rotation stiffness reduce energy cost of arm swing.
    Exercises:
      1. Push-Up (PUSH_UP/PUSH_UP) 3x12 — push pattern, chest/triceps
      2. Pike Push-Up (PUSH_UP/PIKE_PUSH_UP) 3x10 — overhead/shoulder strength, running posture
      3. Pull-Up (PULL_UP/PULL_UP) 3x6 — vertical pull, upper back, posture
      4. Plank (PLANK/PLANK) 3x45sec — anterior core, spine stiffness = energy transfer
      5. Side Plank (PLANK/SIDE_PLANK) 2x30sec each — lateral stability, hip offloading
      6. Bicycle Crunch (SIT_UP/BICYCLE_CRUNCH) 3x20 — rotational core, running-specific
    """
    o = 1
    g = 1

    def next_o():
        nonlocal o
        v = o
        o += 1
        return v

    def next_g():
        nonlocal g
        v = g
        g += 1
        return v

    steps = []

    # 1. Push-Up 3x12
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 12, "PUSH_UP", "PUSH_UP",
                "Push-up. Full range, chest to fist-height. Body plank throughout."),
        rest(next_o(), gid),
    ]))

    # 2. Pike Push-Up 3x10
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 10, "PUSH_UP", "PIKE_PUSH_UP",
                "Pike push-up. Hips high, head toward floor. Shoulder dominant."),
        rest(next_o(), gid),
    ]))

    # 3. Pull-Up 3x6
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 6, "PULL_UP", "PULL_UP",
                "Pull-up. Full hang to chin over bar. Control the descent."),
        rest(next_o(), gid),
    ]))

    # 4. Plank 3x45sec
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_time(next_o(), gid, 45, "PLANK", "PLANK",
                "Plank. Elbows under shoulders. Squeeze glutes + abs. Breathe."),
        rest(next_o(), gid),
    ]))

    # 5. Side Plank 2x30sec each
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 2, [
        ex_time(next_o(), gid, 30, "PLANK", "SIDE_PLANK",
                "Side plank. 30sec each side. Hips stacked, don't sag."),
        rest(next_o(), gid),
    ]))

    # 6. Bicycle Crunch 3x20
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 20, "SIT_UP", "BICYCLE_CRUNCH",
                "Bicycle crunch. Slow, controlled. Opposite elbow to knee."),
        rest(next_o(), gid),
    ]))

    return workout(
        "Upper Body + Core: Running Economy",
        "Arm/trunk strength for running economy. Evidence: concurrent strength training "
        "improves running economy 2-4% over 12-16 weeks. Pull-up needs a bar. "
        "Plank = time-based. Rest 60-90sec between sets (press lap).",
        STRENGTH, steps, 2400,
    )


def full_body_posterior_chain():
    """
    Full Body: Posterior Chain & Hip Hinge — 45min
    Focus: Single-leg mechanics, hip hinge pattern, posterior chain activation
    Science: Proximal hip strength (glute max/med) is the primary biomechanical
             intervention for PTT and overstriding correction. Single-leg work
             trains the exact motor pattern used in running gait.
    Exercises:
      1. Walking Lunge (LUNGE/WALKING_LUNGE) 3x12 each — sport-specific, hip dominant
      2. Single-Leg Deadlift (DEADLIFT/SINGLE_LEG_BARBELL_DEADLIFT) 3x8 each — posterior chain + balance
      3. Step-Up (SQUAT/DUMBBELL_STEP_UP) 3x12 each — glute/quad, running-specific push
      4. Wide Push-Up (PUSH_UP/WIDE_PUSH_UP) 3x12 — chest/anterior deltoid
      5. Crunch (SIT_UP/CRUNCH) 3x20 — anterior core
      6. Single-Leg Hip Raise (HIP_RAISE/SINGLE_LEG_HIP_RAISE) 3x15 each — glute endurance
    """
    o = 1
    g = 1

    def next_o():
        nonlocal o
        v = o
        o += 1
        return v

    def next_g():
        nonlocal g
        v = g
        g += 1
        return v

    steps = []

    # 1. Walking Lunge 3x12 each
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 12, "LUNGE", "WALKING_LUNGE",
                "Walking lunge. 12 steps each leg. Drive forward with glute."),
        rest(next_o(), gid),
    ]))

    # 2. Single-Leg Deadlift 3x8 each
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 8, "DEADLIFT", "SINGLE_LEG_BARBELL_DEADLIFT",
                "Single-leg deadlift bodyweight. 8 each leg. Hip hinge, back flat. Balance focus."),
        rest(next_o(), gid),
    ]))

    # 3. Step-Up 3x12 each
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 12, "SQUAT", "DUMBBELL_STEP_UP",
                "Step-up on chair/box. 12 each leg. Drive through heel. No push off back foot."),
        rest(next_o(), gid),
    ]))

    # 4. Wide Push-Up 3x12
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 12, "PUSH_UP", "WIDE_PUSH_UP",
                "Wide-grip push-up. Hands wider than shoulders. Chest leads."),
        rest(next_o(), gid),
    ]))

    # 5. Crunch 3x20
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 20, "SIT_UP", "CRUNCH",
                "Crunch. Hands behind head, elbows wide. Lower back stays grounded."),
        rest(next_o(), gid),
    ]))

    # 6. Single-Leg Hip Raise 3x15
    gid = next_g()
    steps.append(rep_group(next_o(), gid, 3, [
        ex_reps(next_o(), gid, 15, "HIP_RAISE", "SINGLE_LEG_HIP_RAISE",
                "Single-leg glute bridge. 15 each side. Full hip extension, 1sec hold at top."),
        rest(next_o(), gid),
    ]))

    return workout(
        "Full Body: Posterior Chain & Hip Hinge",
        "Single-leg mechanics + posterior chain. Running-specific motor patterns. "
        "Single-leg deadlift = bodyweight, focus on hip hinge + balance. "
        "Step-up on a sturdy chair (30-40cm). Rest 90sec between sets (press lap).",
        STRENGTH, steps, 2700,
    )


# ─── Upload ──────────────────────────────────────────────────────────────────

def main():
    print("Connecting to Garmin Connect...")
    client = Garmin()
    client.login(str(TOKEN_DIR))
    print("Connected.\n")

    workouts = [
        ("Walk-Run Return Protocol", walk_run_protocol()),
        ("Z2 Base Builder", z2_easy_run()),
        ("Lower Body: Hip & Glute", lower_body_hip_glute()),
        ("Upper Body + Core", upper_body_core()),
        ("Full Body: Posterior Chain", full_body_posterior_chain()),
    ]

    results = []
    for label, w in workouts:
        print(f"Uploading: {label}...")
        try:
            result = client.upload_workout(w)
            wid = result.get("workoutId", "?")
            print(f"  [OK] Uploaded - workoutId: {wid}")
            results.append({"name": label, "workoutId": wid, "status": "ok"})
        except Exception as e:
            print(f"  [FAIL] Failed: {e}")
            results.append({"name": label, "status": "error", "error": str(e)})

    print("\n─── Summary ─────────────────────────────────────────────────────")
    for r in results:
        icon = "[OK]" if r["status"] == "ok" else "[FAIL]"
        detail = f"id={r['workoutId']}" if r["status"] == "ok" else r.get("error", "")
        print(f"  {icon}  {r['name']:<40} {detail}")
    print("\nSync your watch via Garmin Connect app to see workouts.")


if __name__ == "__main__":
    main()

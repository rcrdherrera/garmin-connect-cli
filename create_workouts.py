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

import sys
from pathlib import Path

from garminconnect import Garmin

TOKEN_DIR = Path.home() / ".config" / "garmin-connect-cli" / "tokens"

# Primitives (sport types, step-type/condition constants, _base_step, ex_reps,
# ex_time, rest, run_seg, rep_group, workout) now live in workout_builder.py -
# this used to be an independent, drifting copy of the same code.
sys.path.insert(0, str(Path(__file__).parent / "src"))
from garmin_connect_cli.workout_builder import (  # noqa: E402
    RUNNING,
    STEP_COOLDOWN,
    STEP_INTERVAL,
    STEP_RECOVERY,
    STEP_WARMUP,
    STRENGTH,
    ex_reps,
    ex_reps_w,
    ex_time,
    rep_group,
    rest,
    run_seg,
    workout,
)

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
        rep_group(
            2,
            1,
            5,
            [
                run_seg(
                    3,
                    STEP_INTERVAL,
                    120,
                    "RUN — HR target <155. Cadence 168 spm. Light, quick steps.",
                    child=1,
                ),
                run_seg(4, STEP_RECOVERY, 60, "WALK recovery. Breathe, let HR drop.", child=1),
            ],
        ),
        run_seg(5, STEP_COOLDOWN, 300, "Walk cool-down. Easy pace."),
    ]
    return workout(
        "Return Protocol: Walk-Run",
        "PTT return protocol. 5x (2min run / 1min walk). HR<155 bpm. "
        "Cadence target 168 spm — use metronome. No pain = green light to progress.",
        RUNNING,
        steps,
        1500,
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
        run_seg(
            2,
            STEP_INTERVAL,
            1200,
            "Easy run. HR 145-162 (Z2). Cadence 168-172 spm. Conversational pace. "
            "If PTT feels anything, drop to walk immediately.",
        ),
        run_seg(3, STEP_COOLDOWN, 300, "Walk cool-down. Calf stretch after."),
    ]
    return workout(
        "Z2 Base Builder — Easy Run",
        "Aerobic base session. HR 145-162 (Z2, below LT1 162 bpm). "
        "Cadence 168-172 spm. 20min continuous — stop if any PTT discomfort.",
        RUNNING,
        steps,
        1800,
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
    steps.append(
        rep_group(
            rg_o,
            gid,
            4,
            [
                ex_reps(
                    next_o(),
                    gid,
                    15,
                    "HIP_RAISE",
                    "BRIDGE",
                    "Glute bridge. Squeeze at top 1sec. Pelvis neutral.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 2. Single-Leg Hip Raise 3x12
    gid = next_g()
    rg_o = next_o()
    steps.append(
        rep_group(
            rg_o,
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    12,
                    "HIP_RAISE",
                    "SINGLE_LEG_HIP_RAISE",
                    "Single-leg glute bridge. 12 each side. Keep hips level.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 3. Split Squat 3x10 each
    gid = next_g()
    rg_o = next_o()
    steps.append(
        rep_group(
            rg_o,
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    10,
                    "SQUAT",
                    "SPLIT_SQUAT",
                    "Split squat. 10 each leg. Front knee tracks toe. Upright torso.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 4. Reverse Lunge 3x10 each
    gid = next_g()
    rg_o = next_o()
    steps.append(
        rep_group(
            rg_o,
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    10,
                    "LUNGE",
                    "REVERSE_LUNGE",
                    "Reverse lunge. 10 each leg. Step back, lower knee to floor.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 5. Calf Raise 3x15 slow eccentric
    gid = next_g()
    rg_o = next_o()
    steps.append(
        rep_group(
            rg_o,
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    15,
                    "CALF_RAISE",
                    "STANDING_CALF_RAISE",
                    "Calf raise. Rise 1sec, LOWER 3sec (eccentric focus). Tendon rehab.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    return workout(
        "Lower Body: Hip & Glute — PTT Focus",
        "PTT rehab strength. Glute/hip work offloads the posterior tibial tendon. "
        "Eccentric calf lowers (3sec down) rebuild tendon collagen. 3-4 sets each. "
        "Rest 90-120sec between sets (press lap). STOP if any PTT pain.",
        STRENGTH,
        steps,
        2700,
    )


def lower_body_hip_glute_bands():
    """
    Lower Body: Hip, Glute, Tibialis & Bands — PTT Focus — ~55min

    Enhanced lower session that adds the hip-band + ankle-strap equipment to the
    proven Hip/Glute/Tibialis template. New vs. the older version:
      - Lateral band walk (hip loop) — direct glute-medius/abductor loading. Weak
        abductors -> femoral internal rotation -> pronation -> PTT overload
        (Semciw et al.), so this is a primary PTT offloader, not accessory work.
      - Weighted lying leg raise (ankle strap) — hip-flexor strength for swing phase.

    Exercises (all validated against Garmin's catalog + owned equipment):
      1. Lateral Band Walk (BANDED_EXERCISES/LATERAL_BAND_WALKS) 3x12/side — glute-med activation
      2. Glute Bridge (HIP_RAISE, 10kg) 4x15 — glute max, key PTT offloader
      3. Single-Leg Hip Raise (HIP_RAISE/SINGLE_LEG_HIP_RAISE) 3x12/side — unilateral glute
      4. Split Squat (SQUAT, 8kg) 3x10/side — hip/quad, single-leg
      5. Reverse Lunge (LUNGE, 8kg) 3x10/side — glute dominant, knee-safe
      6. Weighted Lying Leg Raise (LEG_RAISE/WEIGHTED_LYING_STRAIGHT_LEG_RAISE, 4kg ankle strap) 3x12/side — hip flexor
      7. Standing Calf Raise (CALF_RAISE/STANDING_CALF_RAISE, 10kg) 3x15 slow eccentric — tendon durability
      8. Tibialis Raise (tibial bar, incline bench) 3x15 slow eccentric — pronation control
    """
    o = 1

    def next_o():
        nonlocal o
        v = o
        o += 1
        return v

    g = 1

    def next_g():
        nonlocal g
        v = g
        g += 1
        return v

    steps = []

    # 1. Lateral Band Walk 3x12 each — glute-med activation (hip loop)
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    12,
                    "BANDED_EXERCISES",
                    "LATERAL_BAND_WALKS",
                    "Hip loop above knees. 12 steps each way. Stay low, toes forward, keep band tension.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 2. Glute Bridge 4x15 @ 10kg
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            4,
            [
                ex_reps_w(
                    next_o(),
                    gid,
                    15,
                    "HIP_RAISE",
                    None,
                    10.0,
                    "Glute bridge. KB/DB on hips (10kg). Squeeze 1s at top. Pelvis neutral.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 3. Single-Leg Hip Raise 3x12 each (bodyweight)
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    12,
                    "HIP_RAISE",
                    "SINGLE_LEG_HIP_RAISE",
                    "Single-leg glute bridge. 12 each side. Keep hips level, control the descent.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 4. Split Squat 3x10 each @ 8kg
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps_w(
                    next_o(),
                    gid,
                    10,
                    "SQUAT",
                    None,
                    8.0,
                    "Split squat. DB in each hand (8kg). 10 each leg. Front knee tracks toe, upright torso.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 5. Reverse Lunge 3x10 each @ 8kg
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps_w(
                    next_o(),
                    gid,
                    10,
                    "LUNGE",
                    None,
                    8.0,
                    "Reverse lunge. DB in each hand (8kg). 10 each leg. Step back, drive through front heel.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 6. Weighted Lying Leg Raise 3x12 each @ 4kg (ankle strap) — hip flexor
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps_w(
                    next_o(),
                    gid,
                    12,
                    "LEG_RAISE",
                    "WEIGHTED_LYING_STRAIGHT_LEG_RAISE",
                    4.0,
                    "Ankle strap + DB (start 4kg). Lying, straight leg raise. 12 each leg. Slow, no swinging.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 7. Standing Calf Raise 3x15 @ 10kg, slow eccentric
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps_w(
                    next_o(),
                    gid,
                    15,
                    "CALF_RAISE",
                    "STANDING_CALF_RAISE",
                    10.0,
                    "Hold KB/DB (10kg). Rise 1s, LOWER 3s eccentric. Tendon durability.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 8. Tibialis Raise 3x15, slow eccentric (tibial bar, not in Garmin vocab -> desc only)
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    15,
                    "CALF_RAISE",
                    None,
                    "Feet on incline bench, tibial bar loaded. Lift toes UP, LOWER 3s eccentric. Tibialis anterior — pronation control.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    return workout(
        "Lower Body: Hip, Glute, Tibialis & Bands — PTT Focus",
        "PTT lower session. Band walks load the glute medius (offloads the tendon); ankle-strap "
        "leg raises add hip-flexor strength; eccentric calf + tibialis raises (3s down) build tendon "
        "durability. Rest 90-120sec between sets (press lap). STOP if any PTT pain.",
        STRENGTH,
        steps,
        3300,
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
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    12,
                    "PUSH_UP",
                    "PUSH_UP",
                    "Push-up. Full range, chest to fist-height. Body plank throughout.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 2. Pike Push-Up 3x10
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    10,
                    "PUSH_UP",
                    "PIKE_PUSH_UP",
                    "Pike push-up. Hips high, head toward floor. Shoulder dominant.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 3. Pull-Up 3x6
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    6,
                    "PULL_UP",
                    "PULL_UP",
                    "Pull-up. Full hang to chin over bar. Control the descent.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 4. Plank 3x45sec
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_time(
                    next_o(),
                    gid,
                    45,
                    "PLANK",
                    "PLANK",
                    "Plank. Elbows under shoulders. Squeeze glutes + abs. Breathe.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 5. Side Plank 2x30sec each
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            2,
            [
                ex_time(
                    next_o(),
                    gid,
                    30,
                    "PLANK",
                    "SIDE_PLANK",
                    "Side plank. 30sec each side. Hips stacked, don't sag.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 6. Bicycle Crunch 3x20
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    20,
                    "SIT_UP",
                    "BICYCLE_CRUNCH",
                    "Bicycle crunch. Slow, controlled. Opposite elbow to knee.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    return workout(
        "Upper Body + Core: Running Economy",
        "Arm/trunk strength for running economy. Evidence: concurrent strength training "
        "improves running economy 2-4% over 12-16 weeks. Pull-up needs a bar. "
        "Plank = time-based. Rest 60-90sec between sets (press lap).",
        STRENGTH,
        steps,
        2400,
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
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    12,
                    "LUNGE",
                    "WALKING_LUNGE",
                    "Walking lunge. 12 steps each leg. Drive forward with glute.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 2. Single-Leg Deadlift 3x8 each
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    8,
                    "DEADLIFT",
                    "SINGLE_LEG_BARBELL_DEADLIFT",
                    "Single-leg deadlift bodyweight. 8 each leg. Hip hinge, back flat. Balance focus.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 3. Step-Up 3x12 each
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    12,
                    "SQUAT",
                    "DUMBBELL_STEP_UP",
                    "Step-up on chair/box. 12 each leg. Drive through heel. No push off back foot.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 4. Wide Push-Up 3x12
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    12,
                    "PUSH_UP",
                    "WIDE_PUSH_UP",
                    "Wide-grip push-up. Hands wider than shoulders. Chest leads.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 5. Crunch 3x20
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    20,
                    "SIT_UP",
                    "CRUNCH",
                    "Crunch. Hands behind head, elbows wide. Lower back stays grounded.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    # 6. Single-Leg Hip Raise 3x15
    gid = next_g()
    steps.append(
        rep_group(
            next_o(),
            gid,
            3,
            [
                ex_reps(
                    next_o(),
                    gid,
                    15,
                    "HIP_RAISE",
                    "SINGLE_LEG_HIP_RAISE",
                    "Single-leg glute bridge. 15 each side. Full hip extension, 1sec hold at top.",
                ),
                rest(next_o(), gid),
            ],
        )
    )

    return workout(
        "Full Body: Posterior Chain & Hip Hinge",
        "Single-leg mechanics + posterior chain. Running-specific motor patterns. "
        "Single-leg deadlift = bodyweight, focus on hip hinge + balance. "
        "Step-up on a sturdy chair (30-40cm). Rest 90sec between sets (press lap).",
        STRENGTH,
        steps,
        2700,
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
        ("Lower Body: Hip, Glute, Tibialis & Bands", lower_body_hip_glute_bands()),
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

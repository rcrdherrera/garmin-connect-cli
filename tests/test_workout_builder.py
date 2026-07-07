"""Tests for garmin_connect_cli.workout_builder.

Pure/offline - no Garmin API involved. validate_exercise reads the
committed data/garmin_exercises_equipment.json and data/my_equipment.json
files directly.
"""

from __future__ import annotations

from garmin_connect_cli.workout_builder import (
    STEP_COOLDOWN,
    STEP_WARMUP,
    StepSequencer,
    build_curated_catalog,
    ex_reps,
    ex_reps_w,
    ex_time,
    rest,
    run_seg,
    validate_exercise,
)


class TestStepSequencer:
    def test_standalone_allocates_sequential_order(self) -> None:
        seq = StepSequencer()
        warmup = seq.standalone(lambda o: run_seg(o, STEP_WARMUP, 300, "warmup"))
        cooldown = seq.standalone(lambda o: run_seg(o, STEP_COOLDOWN, 180, "cooldown"))
        assert warmup["stepOrder"] == 1
        assert cooldown["stepOrder"] == 2
        assert warmup["childStepId"] is None
        assert cooldown["childStepId"] is None

    def test_block_wraps_steps_in_rep_group_with_shared_child_id(self) -> None:
        seq = StepSequencer()
        group = seq.block(
            3,
            lambda o, c: [
                ex_reps(o(), c, 12, "PUSH_UP", "PUSH_UP", "push-up"),
                rest(o(), c),
            ],
        )
        assert group["type"] == "RepeatGroupDTO"
        assert group["numberOfIterations"] == 3
        inner = group["workoutSteps"]
        assert len(inner) == 2
        assert all(step["childStepId"] == 1 for step in inner)
        # stepOrder allocated after the group's own order (1), so inner steps start at 2
        assert group["stepOrder"] == 1
        assert [s["stepOrder"] for s in inner] == [2, 3]

    def test_stepOrder_is_globally_sequential_across_blocks(self) -> None:
        seq = StepSequencer()
        steps = [seq.standalone(lambda o: run_seg(o, STEP_WARMUP, 300, "warmup"))]
        steps.append(
            seq.block(
                3,
                lambda o, c: [
                    ex_reps(o(), c, 12, "PUSH_UP", "PUSH_UP", "push-up"),
                    rest(o(), c),
                ],
            )
        )
        steps.append(
            seq.block(
                2,
                lambda o, c: [
                    ex_time(o(), c, 45, "PLANK", "PLANK", "plank"),
                    rest(o(), c),
                ],
            )
        )
        steps.append(seq.standalone(lambda o: run_seg(o, STEP_COOLDOWN, 180, "cooldown")))

        all_orders = []
        for step in steps:
            all_orders.append(step["stepOrder"])
            if step["type"] == "RepeatGroupDTO":
                all_orders.extend(s["stepOrder"] for s in step["workoutSteps"])
        assert all_orders == sorted(all_orders)
        assert len(all_orders) == len(set(all_orders))  # no duplicates

    def test_childStepId_increments_once_per_block(self) -> None:
        seq = StepSequencer()
        block1 = seq.block(3, lambda o, c: [ex_reps(o(), c, 12, "PUSH_UP", "PUSH_UP")])
        block2 = seq.block(2, lambda o, c: [ex_time(o(), c, 45, "PLANK", "PLANK")])
        assert block1["childStepId"] == 1
        assert block2["childStepId"] == 2
        assert block1["workoutSteps"][0]["childStepId"] == 1
        assert block2["workoutSteps"][0]["childStepId"] == 2


class TestValidateExercise:
    def test_none_none_is_valid(self) -> None:
        assert validate_exercise(None, None) == []

    def test_mismatched_none_is_invalid(self) -> None:
        assert validate_exercise("PUSH_UP", None) != []
        assert validate_exercise(None, "PUSH_UP") != []

    def test_known_good_bodyweight_exercise_is_valid(self) -> None:
        assert validate_exercise("PUSH_UP", "PUSH_UP") == []

    def test_known_good_owned_equipment_exercise_is_valid(self) -> None:
        # DUMBBELL_STEP_UP needs BOX + DUMBBELL, both in data/my_equipment.json
        assert validate_exercise("SQUAT", "DUMBBELL_STEP_UP") == []

    def test_rejected_exercise_name_warns(self) -> None:
        # HIP_RAISE/BRIDGE is not in Garmin's own exercise catalog
        warnings = validate_exercise("HIP_RAISE", "BRIDGE")
        assert warnings
        assert "catalog" in warnings[0]

    def test_unowned_equipment_warns(self) -> None:
        # Today's actual bug: BARBELL_ROW/OVERHEAD_BARBELL_PRESS/CHIN_UP are all
        # valid Garmin exercise names but require equipment not in the home gym.
        for category, name in [
            ("ROW", "BARBELL_ROW"),
            ("SHOULDER_PRESS", "OVERHEAD_BARBELL_PRESS"),
            ("PULL_UP", "CHIN_UP"),
        ]:
            warnings = validate_exercise(category, name)
            assert warnings, f"{category}/{name} should warn about unowned equipment"
            assert "equipment" in warnings[0].lower()


class TestWeightConvention:
    def test_ex_reps_w_passes_weight_kg_through_unchanged(self) -> None:
        # Confirmed against the live Garmin Connect app (2026-07-06): weightValue
        # is kg directly, NOT grams, despite KG_UNIT's factor=1000.0. Do not
        # "fix" this to multiply by 1000 again.
        step = ex_reps_w(1, 1, 10, "SQUAT", "DUMBBELL_STEP_UP", 16.0, "step-up")
        assert step["weightValue"] == 16.0

    def test_ex_reps_is_bodyweight_sentinel(self) -> None:
        step = ex_reps(1, 1, 12, "PUSH_UP", "PUSH_UP")
        assert step["weightValue"] == -1.0


class TestBuildCuratedCatalog:
    def test_only_includes_equipment_owned_exercises(self) -> None:
        catalog = build_curated_catalog()
        # PUSH_UP is bodyweight - should always be present
        assert "PUSH_UP" in catalog
        assert "PUSH_UP" in catalog["PUSH_UP"]
        # every exercise in every category must pass validate_exercise cleanly
        for category, names in catalog.items():
            for name in names:
                assert validate_exercise(category, name) == [], f"{category}/{name} should be valid"

    def test_excludes_barbell_and_pullup_only_exercises(self) -> None:
        catalog = build_curated_catalog()
        assert "BARBELL_ROW" not in catalog.get("ROW", [])
        assert "CHIN_UP" not in catalog.get("PULL_UP", [])
        assert "OVERHEAD_BARBELL_PRESS" not in catalog.get("SHOULDER_PRESS", [])

    def test_skip_categories_excludes_named_categories(self) -> None:
        full = build_curated_catalog()
        assert "PUSH_UP" in full
        filtered = build_curated_catalog(skip_categories=frozenset({"PUSH_UP"}))
        assert "PUSH_UP" not in filtered

    def test_step_up_variants_included_via_box_equivalence(self) -> None:
        # data/my_equipment.json treats the bench as equivalent to Garmin's BOX tag
        catalog = build_curated_catalog()
        assert "DUMBBELL_STEP_UP" in catalog.get("SQUAT", [])

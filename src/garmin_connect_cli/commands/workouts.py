"""Workout library and calendar scheduling commands."""

from __future__ import annotations

from typing import Annotated

import typer

from garmin_connect_cli.client import GarminClient
from garmin_connect_cli.core import emit, emit_result, with_client

app = typer.Typer(no_args_is_help=True)


@app.command("list")
@with_client
def list_workouts(
    client: GarminClient,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum number of workouts to return"),
    ] = 20,
    start: Annotated[
        int,
        typer.Option("--start", "-s", help="Start index for pagination"),
    ] = 0,
) -> None:
    """List workouts in the Garmin workout library.

    Examples:
        garmin-connect workouts list
        garmin-connect workouts list --limit 50
    """
    data = client.client.get_workouts(start=start, limit=limit)
    emit(data)


@app.command("schedule")
@with_client
def schedule_workout(
    client: GarminClient,
    workout_id: Annotated[int, typer.Argument(help="Garmin workout library ID")],
    date: Annotated[str, typer.Argument(help="Target date (YYYY-MM-DD)")],
) -> None:
    """Schedule a workout from the library to a specific calendar date.

    The workout must already exist in the Garmin workout library (uploaded via /coach).
    After scheduling it will appear on your Garmin Connect calendar and sync to your watch.

    Examples:
        garmin-connect workouts schedule 12345678 2026-05-20
    """
    result = client.schedule_workout(workout_id, date)
    scheduled_id = result.get("scheduledWorkoutId") if isinstance(result, dict) else None
    emit_result(
        result,
        f"Scheduled workout {workout_id} on {date} (scheduled_id={scheduled_id})",
    )


@app.command("unschedule")
@with_client
def unschedule_workout(
    client: GarminClient,
    scheduled_workout_id: Annotated[
        int, typer.Argument(help="Scheduled workout ID (from schedule response)")
    ],
) -> None:
    """Remove a workout from the Garmin calendar.

    Note: uses the scheduledWorkoutId returned by 'workouts schedule', not the library ID.

    Examples:
        garmin-connect workouts unschedule 87654321
    """
    client.delete_scheduled_workout(scheduled_workout_id)
    emit_result({}, f"Removed scheduled workout {scheduled_workout_id} from calendar")


@app.command("evaluation")
@with_client
def get_evaluation(
    client: GarminClient,
    activity_id: Annotated[
        int | None,
        typer.Argument(help="Activity ID (omit for most recent activity)"),
    ] = None,
) -> None:
    """Get post-workout self-evaluation (feel + RPE) for a completed activity.

    Reads the feel and RPE values you entered in Garmin Connect after the workout.
    Feel: terrible / normal / good / excellent
    RPE: 0-10 scale (1=very easy, 10=maximum effort)

    Examples:
        garmin-connect workouts evaluation
        garmin-connect workouts evaluation 22861653356
    """
    if activity_id is None:
        activities = client.get_activities(start=0, limit=1)
        if not activities:
            typer.echo("error: no activities found", err=True)
            raise typer.Exit(1)
        activity_id = activities[0]["activityId"]

    data = client.get_activity_evaluation(activity_id)
    emit(data)

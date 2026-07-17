# Memory Index

- [User role and goals](user_role.md) — Running coach/training analyst, wants Garmin data + Claude for evidence-based coaching
- [Garmin data access setup](project_setup.md) — CLI working via browser_auth.py workaround; key commands and known data gaps documented
- [Training history and injury context](training_history.md) — Full year analysis: PTT injury, 9-month accumulation, low cadence (153 spm), fitness markers, return-to-run context
- [HR zones and LT methodology](hr_zones.md) — Finalized Garmin zones: Z2 top=162 (LT1), Z4 bottom=174 (LT2), Z5 bottom=182 (95% HRmax=191); dual-threshold 5-zone model, science-backed
- [GarminCoach iOS App](ios_app_project.md) — Swift/HealthKit/Claude app at C:\Users\ricar\Github\Garmin-Coach (github.com/rcrdherrera/Garmin-Coach); all source files written, needs Mac+Xcode to compile
- [2026 Race Goals and Periodization](race_goals_2026.md) — Half Jul 12 (Z2 training run) + Marathon Aug 30 (completion, no PR) + Backyard Ultra Sep 19 (fun/solo, 4–6 laps); now in Phase 2 deload / Phase 3 starts Jun 28
- [Dev environment and tooling](dev_environment.md) — Warp terminal on Windows; jq required for Warp plugin (winget install jqlang.jq); two-repo sync friction; Mac migration under consideration
- [Git remote rule](feedback_git_remote.md) — garmin-connect-cli must push to `personal` remote (fork), never `origin` (upstream eddmann repo)
- [Home gym equipment](home_gym_equipment.md) — DBs/KBs up to 10kg, bench, elastic bands, tibial bar + incline bench; no pull-up bar; tibial raises in every lower body session
- [Strength scheduling framework](strength_framework.md) — Place strength around runs: Lower+PTT on quality day (Tue), Upper on easy day (Thu), 2×/week in build; reuse templates 1633885839 (lower w/ tibialis + bands/strap) + 1579706556 (upper); fetch calendar via `garmin-connect calendar show`
- [Server infrastructure and known bugs](project_server_setup.md) — Ubuntu deployment, self-hosted runner, daily DB sync timer, readiness parsing bug fixed, error logging added
- [Workout upload disabled](feedback_workout_upload.md) — Do NOT upload to Garmin until exercise dict is validated against Garmin FIT SDK library

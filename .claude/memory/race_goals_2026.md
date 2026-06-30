---
name: 2026 race goals and periodization
description: Target races for 2026 season with dates, goals, and phase-by-phase training structure anchored to PTT clearance date
type: project
originSessionId: a90608d6-6302-474f-8588-3a5db040d9c2
---
## Target Races — 2026

| Race | Date | Goal | Constraint |
|------|------|------|------------|
| XIX BBVA Mexico City Half Marathon | 2026-07-12 | Z2 training run — NOT racing | 8 weeks from PTT clearance, hilly course, too soon to race |
| XLIII Telcel Mexico City Marathon | 2026-08-30 | Completion goal, Z2 throughout — NOT a PR attempt | 15.5 weeks from clearance, primary A-race of the season |
| Backyard Ultra | 2026-09-19 | Solo, just for fun — 4–6 laps max, easy shuffle | 20 days post-marathon; PTT risk if marathon is run hard |

**Why:** This is a return year — no PRs, no racing, just healthy completion across all three events. Half marathon is a PTT confidence check within the marathon build. Marathon is the A-race but still a completion/Z2 goal, not a time goal. Backyard is a fun social event 20 days post-marathon — marathon execution directly determines how many backyard laps are safe (conservative marathon = faster recovery = more laps possible). All three events are subordinate to arriving at each start line healthy.

**How to apply:** When planning any session, always ask "does this support arriving at Aug 30 healthy?" If volume, intensity, or frequency is aggressive enough to risk PTT re-aggravation, pull back.

## Course Notes

**Half Marathon (Jul 12):**
- Start: Hemiciclo a Benito Juárez
- Hilly course — downhills increase eccentric PTT load
- Altitude: ~2,240m (fully acclimatized)
- Run at 6:10–6:30/km (Z2). If any PTT discomfort at km 5 → DNS/DNF, no exceptions.

**Marathon (Aug 30):**
- Start: Estadio Olímpico Universitario → Finish: Zócalo Capitalino
- Significant elevation change km 10–25 — highest PTT/overstriding risk zone
- Cadence discipline on hills is critical (stay 168+ spm on downhills)
- Realistic finish time given return-to-run context: 3:50–4:15 (not a time goal, just expectation setting)

## Current Status (as of 2026-05-17)
**PTT clearance achieved 2026-05-16. Phase 1 (Return to Run) is now active — Day 2.**

## Periodization Structure (anchored to 2026-05-16 clearance)

### Phase 1 — Return to Run (May 16 – Jun 6, weeks 1–3)
- Volume: 15 → 25km/week
- Sessions: 3 runs/week, every other day
- Format: Walk-run → Z2 continuous
- HR: ≤162 bpm (Z2 ceiling)
- Cadence: 168 spm from day 1
- Strength: 3×/week (lower/upper/full rotation), eccentric calf every lower session
- Deload: Week 3 = 50% volume (~12km)

### Phase 2 — Base Build (Jun 7 – Jun 27, weeks 4–6)
- Volume: 25 → 38km/week
- Sessions: 4 runs/week, introduce mid-week medium run (10–12km)
- Long run: build to 14–16km at Z2
- HR: full Z2 (145–162). Introduce 4–6 × 30sec Z3 surges in one run per week (week 5+)
- Cadence target: 168–172 spm
- Deload: Week 6 = 50% volume (~18km)

### Phase 3 — Half Marathon Prep (Jun 28 – Jul 12, weeks 7–8)
- Volume: 35–40km/week
- Long run: 16–18km (week 7), then half marathon as the week 8 long run
- Half marathon execution: Z2 pace (6:10–6:30/km), HR ≤162, cadence 168+
- No racing. If PTT hurts at any point → stop immediately.

### Phase 4 — Marathon Build (Jul 13 – Aug 9, weeks 9–13)
- Volume: 40 → 52km/week (10% increase cap, deload every 4th week)
- Long runs: 20km → 28–30km, every 7–10 days
- Introduce one fartlek/tempo session per week from week 10 (Z3, not Z4 yet)
- Z4 threshold only from week 11+ if PTT fully asymptomatic
- Deload: Week 12 = 50% volume (~25km)

### Phase 5 — Taper (Aug 10 – Aug 29, weeks 14–15)
- Volume: drop 40% (to ~28–32km)
- Maintain 2 quality sessions (one Z2 long 16km, one short fartlek)
- No new stress — protect the PTT
- Sleep, nutrition, hydration priority

### Phase 6 — Post-Marathon Recovery & Backyard Prep (Aug 31 – Sep 18)
- Days 1–7: complete rest + walking only. No running. Tendons are remodeling.
- Days 8–14: easy 20–30min jogs only if PTT silent. No volume targets.
- Days 15–20: shuffle pace test runs. If anything hurts → DNS the backyard, no exceptions.
- Backyard (Sep 19): 4–6 laps at easy shuffle pace. Pull out early if PTT speaks up.
- Marathon execution is the key lever: Z2 throughout → faster recovery → safer backyard.

### Race Day (Aug 30)
- Warm up 10–15min easy
- Km 1–30: Z2 (HR 145–162, pace ~5:30–6:00/km at race effort)
- Km 30–42: assess and decide — push to Z3 only if feeling good and PTT silent
- Cadence 168+ spm throughout, especially on downhill sections km 10–25

## Coaching Delivery Model

- Coach loads workouts **monthly** — only the current month's sessions will be on the Garmin calendar
- When analyzing the calendar, never flag "missing future workouts" as a concern if the current month's sessions are present
- Garmin calendar API endpoint: `/calendar-service/year/{year}/month/{month}` (returns `calendarItems[]`)
- The workout library (`/workout-service/workouts`) accumulates all templates ever created — contains old 2024 Galloway-style workouts; focus analysis on 2026 sessions only
- A separate higher-intensity quality session (5×300m @ 5:35/km threshold) exists in the library for Phase 4+ — it should not appear on the calendar before Jul 13

## Key Rules for the Entire Season

1. **Half marathon is Z2 or it's a DNS** — the marathon is worth more than a half PR
2. **Any PTT pain during a run = stop that session, drop back one phase tier**
3. **Deload weeks are non-negotiable** — this athlete's injury pattern is accumulation without recovery
4. **10% volume increase cap per week** — never exceed, even if feeling great
5. **Cadence 168-172 spm must be logged every run** — structural fix, not optional
6. **HRV drop >10% for 2+ days = reduce volume, not intensity** (Kiviniemi protocol)

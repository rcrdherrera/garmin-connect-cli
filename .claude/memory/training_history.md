---
name: Ricardo training history and injury context
description: Full year training analysis, injury timeline, biomechanical findings, and return-to-run context
type: project
originSessionId: 1b0e927b-c50b-4c47-9024-2de3141888bc
---
## Athlete Profile
- Runner since at least April 2025 (data start)
- Ultra runner: completed 42.8km ultra (Aug 31 2025) and Backyard Ultra 45.7km (Nov 15 2025)
- Also runs road races: 12K (May 2025), 10K Jan 4 2026 at 4:28/km
- Training base: 35–50km/week when healthy
- Easy pace: ~6:00–6:20/km at HR ~152–155 bpm
- PTT injury forced stop April 14 2026; physio cleared first treadmill test May 9 2026 — felt great
- Also does HYROX-driven strength training (no tendon impact movements)

## Current Injury Status (updated 2026-05-16)
- **Posterior Tibial Tendon (PTT)** — CLEARED by physio on 2026-05-16. Full return to running approved.
- Physio instruction: go slow, follow the conservative return-to-run protocol already in place
- No active injury — this is now a return-to-run ramp-up phase, not injury management
- Treadmill restriction lifted: outdoor running allowed on flat surfaces
- HR cap still applies for the first 2–3 weeks: stay in Z2 (145–162 bpm), no Z3+ until base is rebuilt
- No speedwork, no hills, no races until 3+ pain-free weeks at 75–80% pre-injury volume
- Cadence work remains mandatory: 168–172 spm to correct overstriding that caused the PTT
- Eccentric calf work continues in every lower body session (tendon durability, not rehab)
- During injury period: HYROX strength training + functional classes maintained fitness base

## Accumulation Timeline (root cause of PTT)
**Note:** PTT injury is not traced back to August 2025 — the pattern pre-Aug is about insufficient recovery between peak events, not the PTT specifically.

1. **Aug 2025:** Vacation → undertrained → ran 42.8km ultra anyway with LOW HRV (64ms).
2. **Post-Aug ultra:** Only 2 weeks recovery then back to 45km+ within 3 weeks.
3. **Nov 2025:** Backyard Ultra 45.7km (72km week) — only 1 week recovery (28km) then immediately 55km.
4. **Dec 2025:** Maintained 50–65km/week through Christmas with no deload.
5. **Jan 4 2026:** 10K race at 4:28/km, then 3–4 weeks of illness. Ran through it at reduced volume.
6. **Feb 2026 W06:** "Kinda injured" — volume collapsed to 7.6km, HRV hit yearly low of 71ms (LOW status). PTT likely emerges around this period.
7. **Feb W07:** Immediately jumped back to 43km without ramp-up.
8. **Feb–Apr 2026:** PTT never fully resolved — volume dipped (10–13km weeks) but always spiked back to 35–43km without adequate recovery.
9. **Apr 14 2026:** PTT forces complete stop.

**Key pattern:** Insufficient recovery between peak events (Aug ultra, Backyard ultra, Jan race). PTT specifically developed Feb–Apr 2026 and was never given time to heal before the final April break.

## Biomechanical Findings
- **Cadence: structurally low — ~153 spm average across the full year** (range 142–162 spm)
  - Low cadence → overstriding → increased pronation loading on PTT every step
  - Low cadence at tempo pace is especially risky (Sep 2025: 146 spm at 5:07/km)
  - During ultras, cadence drops further with fatigue (Backyard: 142 spm)
  - March 2026 race hit 162 spm — capacity exists, just not trained
  - **DURABILITY BREAKTHROUGH (2026-07-25 30k): held 168 spm for the full 30k** with GCT 255ms, stride 93cm controlled, and **L/R ground-contact balance 50.2/49.8 (symmetric)** — cadence did NOT collapse with fatigue for the first time on a long run (contrast Backyard 142 spm), and the injured side showed no offloading. Strongest evidence yet that the structural PTT fix holds under real load, not just on fresh short runs. (This 30k = first run on the new HRM 600 chest strap — see Devices note; balance metric is now trackable every run.)
- **Ground Contact Time: 280–310ms** (high side, especially on easy/treadmill runs; dropped to 255ms on the well-executed 2026-07-25 30k)
- **Stride length: 99–117cm** — varies widely with pace
- Recommended return cadence target: 168–172 spm (not jumping to 180 immediately)
- Garmin metronome tool available: Training → Metronome

## Devices & how metrics are measured (strap upgraded 2026-07-25)
- **Watch: Garmin Fenix 8, 47mm AMOLED** (part `006-B4536-00`).
- **Strap: Garmin HRM 600 (as of 2026-07-25)** — replaced the HRM-Dual, which is no longer used. The HRM 600 is a full running-dynamics chest strap (torso accelerometer), so **cadence + all running dynamics now come from the CHEST STRAP, not the wrist**. First run on it = the **2026-07-25 30k** (confirmed by `groundContactBalanceLeft` being populated for the first time; the wrist sensor can't produce GCT balance).
- **NEW capability unlocked — GCT left/right balance** (previously flagged as wanting a chest strap for exactly this). This is the PTT-side asymmetry monitor. **PTT is on the LEFT leg** (confirmed 2026-07-26). **First reading (2026-07-25 30k): L 50.2% / R 49.8% — essentially perfect symmetry even at 30k under peak fatigue**, and the injured (left) side actually bears a hair *more*, not less → zero protective guarding. Strong durability signal. **Direction rules for future drift:** L dropping below ~48% = left/PTT side being *offloaded/guarded* (subconscious protection — early warning even before pain). L rising above ~52% = healing tendon being *overloaded*. Either persistent drift = investigate before it becomes re-injury.
- **Where the data lives:** activity `summaryDTO` → `averageRunCadence`, `groundContactTime`, `groundContactBalanceLeft`, `strideLength`, `verticalOscillation`, `verticalRatio`. (Top-level `get_activity` keys like `avgRunCadence` return None — read `summaryDTO`.)
- **Cadence caveat (still partly applies):** chest-strap cadence reflects true foot-strike (the old wrist "arm-stall while glancing at watch" artifact is gone — more reliable now). BUT session-average is still **diluted by walk/stop time** (e.g. city-crossing stops on long runs). Do NOT flag a low session-average as overstriding without checking moving time / max cadence / stride length first.
- **Historical note:** runs *before* 2026-07-25 (incl. Jul 21/23) had wrist-based running dynamics + HRM-Dual for HR only — no balance data exists for them, and their cadence/GCT carry the wrist caveats above.

## Fitness Markers (peak and current)
- **Peak fitness: March 2026** — RHR 41 bpm, HRV 97ms/93 weekly avg, 5:00/km race pace
- **Current (May 16, 2026):** HRV BALANCED (101ms last night, 93ms weekly avg), RHR ~49 bpm, readiness 100/100 PRIME
- Detraining from April 14 – May 9 rest period, but fitness bouncing back fast (HRV already back in baseline range)

## HRV Baseline
- Typical balanced range: ~83–103ms
- LOW signals occurred at: Aug 2025 (64ms, post-ultra stress), Feb 2026 (71ms, post-illness spike)
- Rule: if weekly HRV avg drops >10ms below baseline for 3+ days → pull back before injury compounds

## Sleep
- Quantity OK: 7.5–8.5h most nights
- Quality inconsistent: deep sleep often 0.6–1.1h (target 1.5–2h), REM variable
- Deep sleep deficit = impaired tendon repair overnight
- Fix: consistent wake/sleep time, no hard training within 3h of bed

## Weight & Hydration
- Weight: barely tracked (Jul 2025: 76kg, Nov 2025: 79kg)
- Hydration: not tracked at all
- Both need manual logging in Garmin Connect app or a smart scale
- Target: log weight daily same conditions (morning, post-bathroom, pre-food)

## Return to Running Plan Context
- Coach decides on 2026-05-06 (Tuesday)
- Pre-injury baseline: 35–45km/week at ~6:00–6:20/km easy
- Return protocol should start at ~50% volume (18–20km), short runs (5–8km), flat surfaces
- No speedwork or hills until fully pain-free
- Trains by HR feel, not pace: on easy runs Ricardo targets Z2 (HR ≤162 / LT1) by feel — if a prescribed pace (e.g. 6:35–7:14/km) feels too easy and HR is still in Z2, he runs at natural Z2 pace instead. Prescribed pace ranges are estimates, not hard constraints. Never flag "above prescribed pace" as a problem if HR is in range.
- Uses Garmin metronome on every run — cadence during continuous running is actively hitting the target. Low session averages are caused by walk intervals only, not cadence slippage.
- PTT eccentric loading: burning sensation in the PTT/calf during eccentric calf raises is the expected tendon adaptation signal (mechanotransduction). Only flag if pain persists 30+ min after stopping or is present the next morning.
- Cadence work integrated from day 1 of return; current working target 166–168 spm (building toward 168–172 long-term)
- Quality sessions include walk intervals — average session cadence will appear suppressed (~142–155 spm) due to walking portions; this is normal and not a cadence failure
- Lower body strength is always scheduled on Sundays
- Deload weeks (50% volume) every 3–4 weeks are non-negotiable given history

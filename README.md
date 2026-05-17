# Garmin Connect CLI

![Garmin Connect CLI](docs/heading.png)

Garmin Connect from your terminal — pipe it, script it, coach with it.

> A fork of [eddmann/garmin-connect-cli](https://github.com/eddmann/garmin-connect-cli) extended with workout upload, a science-based AI coaching command, and race periodization planning.

---

## What This Fork Adds

| Capability | Description |
|---|---|
| **Workout upload** | Create and push structured workouts (running + strength) directly to Garmin Connect — they sync to your watch automatically |
| **`/coach` Claude Code command** | An evidence-based AI coaching skill that reads your live HRV/readiness data, determines your training phase, builds appropriate workouts, and uploads them in one step |
| **Strength workout support** | Bodyweight and gym strength sessions with Garmin FIT SDK exercise names, sets, reps, and rest prompts on your watch |
| **Race periodization** | Phase-aware training plan anchored to target race dates — the coach automatically prescribes the right intensity and volume for where you are in the plan |
| **Browser auth workaround** | Bypass Garmin's SSO rate-limiting using an existing browser session when normal login fails |

---

## Features

- **All your Garmin data** — activities, stats, sleep, heart rate, HRV, stress, body battery, training status, VO2max, lactate threshold
- **Workout upload** — create structured running and strength workouts programmatically and push to Garmin Connect
- **AI coaching command** — `/coach` reads your live data and builds workouts matched to your current physiological state
- **Script and automate** — composable with `jq`, pipes, `xargs`, and standard Unix tools
- **AI agent ready** — install the agent skill for Claude Code and other compatible assistants
- **Flexible output** — JSON for scripts, CSV for spreadsheets, human-readable tables for the terminal

---

## Installation

### Using uv (recommended)

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rcrdherrera/garmin-connect-cli
cd garmin-connect-cli
uv sync
uv run garmin-connect --help
```

### Quick Install (macOS/Linux binary)

```bash
curl -fsSL https://raw.githubusercontent.com/eddmann/garmin-connect-cli/main/install.sh | sh
```

### Homebrew

```bash
brew install eddmann/tap/garmin-connect-cli
```

---

## Quick Start

```bash
# Authenticate
garmin-connect auth login

# Your data in one call
garmin-connect context

# Recent activities
garmin-connect activities list --limit 10 --type running

# Today's training readiness and HRV
garmin-connect training readiness
garmin-connect training hrv --date-str $(date +%Y-%m-%d)
```

---

## Command Reference

### Global Options

| Flag | Short | Description |
|---|---|---|
| `--format` | `-f` | Output format: `json` (default), `jsonl`, `csv`, `tsv`, `human` |
| `--fields` | | Comma-separated fields to include |
| `--no-header` | | Omit header in CSV/TSV |
| `--verbose` | `-v` | Verbose output to stderr |
| `--quiet` | `-q` | Suppress non-essential output |
| `--profile` | `-p` | Named profile (multi-account) |
| `--version` | `-V` | Show version |

### Authentication

Tokens are stored in `~/.config/garmin-connect-cli/tokens/` and remain valid for ~1 year.

```bash
garmin-connect auth login                 # Interactive login
garmin-connect auth login --email EMAIL   # With credentials
garmin-connect auth status                # Check auth status
garmin-connect auth logout                # Clear tokens
garmin-connect auth login --profile work  # Named profile
```

> **Having trouble logging in?** See [Browser Auth Workaround](#browser-auth-workaround) below.

### Activities

```bash
garmin-connect activities list [--after DATE] [--before DATE] [--limit N] [--type TYPE]
garmin-connect activities get <ID> [--details]
garmin-connect activities splits <ID>
garmin-connect activities download <ID> [--format TCX|GPX|FIT] [-o FILE]
garmin-connect activities upload <FILE>
garmin-connect activities delete <ID> [--force]
```

### Athlete

```bash
garmin-connect athlete           # Profile
garmin-connect athlete stats     # Daily statistics [--date]
garmin-connect athlete summary   # Stats + body metrics [--date]
```

### Health

```bash
garmin-connect health sleep        [--date DATE]
garmin-connect health heart-rate   [--date DATE]
garmin-connect health rhr          [--date DATE]
garmin-connect health steps        [--date DATE]
garmin-connect health stress       [--date DATE]
garmin-connect health body-battery [--date DATE]
```

### Training

```bash
garmin-connect training status    [--date DATE]   # Productive, Peaking, Recovery, etc.
garmin-connect training readiness [--date DATE]   # Score 0-100
garmin-connect training hrv       [--date-str DATE]
garmin-connect training vo2max    [--date DATE]
garmin-connect training lactate                   # Lactate threshold HR and pace
garmin-connect training endurance [--date DATE]
garmin-connect training hill      [--date DATE]
garmin-connect training fitness-age
```

### Weight

```bash
garmin-connect weight list [--start DATE] [--end DATE]
garmin-connect weight get  [--date DATE]
garmin-connect weight log <KG> [--date DATE]
```

### Context (LLM-optimised)

```bash
garmin-connect context                          # Full aggregated context
garmin-connect context --activities 10          # More recent activities
garmin-connect context --focus stats,health     # Specific sections
garmin-connect context --no-health              # Skip health data
```

### Composability

```bash
# Filter runs over 10km
garmin-connect activities list --type running | jq '.[] | select(.distance > 10000)'

# Weekly running volume in km
garmin-connect activities list --after 2026-05-10 --type running \
  | jq '[.[].distance] | add / 1000'

# HRV trend — last 7 days
for d in $(seq 6 -1 0); do
  date=$(date -d "-$d days" +%Y-%m-%d 2>/dev/null || date -v-${d}d +%Y-%m-%d)
  echo -n "$date: "
  garmin-connect training hrv --date-str $date | jq '.hrvSummary.lastNightAvg // "n/a"'
done
```

---

## Workout Upload

Create structured workouts programmatically and push them to Garmin Connect. They appear in your workout library and sync to your watch on the next Bluetooth sync.

### Supported workout types

- **Running** — warmup/interval/recovery/cooldown steps, time or distance based, HR zone targets
- **Strength** — rep-counted or timed exercises, sets, rest prompts, bodyweight or weighted
- **Walk-run intervals** — repeat groups with run/walk alternation, used for return-to-run protocols

### Quick example

```python
from pathlib import Path
from garminconnect import Garmin

client = Garmin()
client.login(str(Path.home() / ".config/garmin-connect-cli/tokens"))

workout = {
    "workoutName": "Easy Z2 Run",
    "sportType": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
    "estimatedDurationInSecs": 1800,
    "workoutSegments": [{
        "segmentOrder": 1,
        "sportType": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
        "workoutSteps": [
            # warmup, interval, cooldown steps...
        ]
    }]
}

result = client.upload_workout(workout)
print(result["workoutId"])
```

See [`create_workouts.py`](create_workouts.py) for a complete working example that builds and uploads 5 science-based workouts (2 running + 3 strength).

### Verified Garmin FIT SDK exercise names

**Lower body (bodyweight)**

| Category | Exercise | Movement |
|---|---|---|
| `HIP_RAISE` | `BRIDGE` | Glute bridge |
| `HIP_RAISE` | `SINGLE_LEG_HIP_RAISE` | Single-leg glute bridge |
| `SQUAT` | `SPLIT_SQUAT` | Split squat |
| `SQUAT` | `DUMBBELL_STEP_UP` | Step-up |
| `LUNGE` | `REVERSE_LUNGE` | Reverse lunge |
| `LUNGE` | `WALKING_LUNGE` | Walking lunge |
| `DEADLIFT` | `SINGLE_LEG_BARBELL_DEADLIFT` | Single-leg RDL |
| `CALF_RAISE` | `STANDING_CALF_RAISE` | Calf raise |

**Upper body & core**

| Category | Exercise | Movement |
|---|---|---|
| `PUSH_UP` | `PUSH_UP` | Standard push-up |
| `PUSH_UP` | `PIKE_PUSH_UP` | Pike push-up |
| `PUSH_UP` | `WIDE_PUSH_UP` | Wide push-up |
| `PUSH_UP` | `DIAMOND_PUSH_UP` | Diamond push-up |
| `PULL_UP` | `PULL_UP` | Pull-up |
| `PULL_UP` | `CHIN_UP` | Chin-up |
| `PLANK` | `PLANK` | Front plank (timed) |
| `PLANK` | `SIDE_PLANK` | Side plank (timed) |
| `SIT_UP` | `CRUNCH` | Crunch |
| `SIT_UP` | `BICYCLE_CRUNCH` | Bicycle crunch |

---

## `/coach` — AI Training Coach

A [Claude Code](https://claude.ai/code) slash command that acts as a science-based running and strength coach. It reads your live Garmin data, determines your current training phase, designs appropriate workouts, and uploads them directly to your Garmin Connect account in one step.

### Setup

Requires [Claude Code](https://claude.ai/code). The command lives at [`.claude/commands/coach.md`](.claude/commands/coach.md) and is automatically available when you open this project in Claude Code.

### Usage

```
/coach              # Full weekly plan — fills what's missing from the week
/coach running      # Running sessions only
/coach strength     # All 3 strength sessions (lower / upper+core / full body)
/coach lower-body   # One lower body session
/coach upper-body   # Upper body + core
/coach full-body    # Posterior chain session
```

### What it does on every invocation

1. **Reads athlete context** — injury status, HR zones (LT1/LT2 anchored), training history, cadence targets, race goals from memory
2. **Fetches live Garmin data** — today's HRV, readiness score (0–100), training status, last 7 days of activities
3. **Calculates current training phase** — based on days since return-to-run clearance and weeks to target races
4. **Makes coaching decisions** using hard gates:
   - Readiness < 40 → rest only, no uploads
   - HRV unbalanced or trending down → drop one intensity tier
   - Active injury protocol → HR caps, cadence cues, no plyometrics
5. **Audits the week** — checks what's been done, fills gaps, avoids doubling up same muscle groups or running on consecutive days during return-to-run
6. **Writes and runs a Python script** — generates workout JSONs using verified Garmin FIT SDK structures and uploads them
7. **Delivers a coaching brief** — readiness state, what was built, why, which day for which session, HR targets, key cues, red flags

### Science foundation

The command is grounded in peer-reviewed research:

| Principle | Source |
|---|---|
| Polarized training (80% Z1–Z2, 20% Z3+) | Seiler & Tønnessen |
| Strength training improves running economy +2–4% | Berryman et al. 2018 meta-analysis |
| Hip/glute weakness → excessive pronation → tendon overload | Semciw et al. 2016 |
| Eccentric tendon loading for collagen synthesis | Alfredson protocol (modified) |
| Cadence retraining: 5–10% increase above baseline | Systematic review, PMC12440572 |
| HRV-guided training load adjustment | Kiviniemi et al. |
| 10% weekly volume increase cap | Standard sports science consensus |

### Training phases (race-anchored)

The coach automatically identifies which phase you're in and constrains intensity accordingly:

| Phase | Weeks | Volume | Key constraint |
|---|---|---|---|
| Return to run | 1–3 | 15–25km | Walk-run → Z2, every other day |
| Base build | 4–6 | 25–38km | Z2 only, long run to 16km |
| Race tune-up | 7–8 | 35–40km | Race as training run (not racing) |
| Marathon build | 9–13 | 40–52km | Long runs to 28–30km, one fartlek/week |
| Taper | 14–15 | 28–32km | 40% volume drop, maintain 2 quality sessions |

---

## Browser Auth Workaround

When Garmin's SSO endpoint rate-limits normal login (HTTP 429), use an existing browser session to extract tokens instead.

### Steps

1. Log in to [connect.garmin.com](https://connect.garmin.com) in your browser
2. Open DevTools → Application → Cookies → `sso.garmin.com`
3. Copy the `CASTGC` cookie value (and any other cookies present)
4. Run the workaround script:

```bash
uv run python browser_auth.py
```

5. Paste the cookies when prompted

The script performs a CAS TGT flow — `GET /sso/login` with the `CASTGC` cookie → ticket → OAuth tokens — which bypasses the rate-limited `POST` endpoint. Tokens are saved to `~/.config/garmin-connect-cli/tokens/` and remain valid for ~1 year.

---

## Configuration

```toml
# ~/.config/garmin-connect-cli/config.toml
[defaults]
format = "json"
limit = 30

[profiles.work]
email = "work@example.com"
```

### Environment variables

| Variable | Description |
|---|---|
| `GARMIN_EMAIL` | Garmin Connect email |
| `GARMIN_PASSWORD` | Garmin Connect password |
| `GARMIN_FORMAT` | Default output format |
| `GARMIN_PROFILE` | Default profile name |
| `GARMIN_CONFIG` | Path to config file |

---

## Development

```bash
git clone https://github.com/rcrdherrera/garmin-connect-cli
cd garmin-connect-cli
make install     # Install dependencies
make test        # Run tests
make lint        # Check linting
make fmt         # Format and auto-fix
```

### Source layout

```
src/garmin_connect_cli/
├── cli.py              # Main Typer app, global options
├── core.py             # State singleton, @with_client decorator, emit()
├── client.py           # GarminClient wrapper with token management (Garth)
├── config.py           # XDG-compliant config (TOML), token path helpers
├── output.py           # Output formatters (JSON, JSONL, CSV, TSV, human)
└── commands/
    ├── activities.py
    ├── athlete.py
    ├── auth.py
    ├── context.py
    ├── health.py
    ├── training.py
    └── weight.py

.claude/commands/
└── coach.md            # /coach Claude Code training command

create_workouts.py      # Example: build and upload 5 science-based workouts
browser_auth.py         # Browser session auth workaround
```

---

## Data Units

| Field | Unit |
|---|---|
| `distance` | meters |
| `duration`, `movingTime` | seconds |
| `averageSpeed`, `maxSpeed` | m/s |
| `elevation` | meters |
| dates | ISO 8601 |
| heart rate | bpm |

---

## Credits

- Original CLI: [eddmann/garmin-connect-cli](https://github.com/eddmann/garmin-connect-cli) by Edd Mann
- Garmin Connect API: [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) by cyberjunky
- Token management: [Garth](https://github.com/matin/garth) by matin

## License

MIT

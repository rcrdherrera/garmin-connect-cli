---
description: Project health dashboard — git, CI, server, and today's Garmin snapshot
allowed-tools: [Bash, Read]
---

# /status — Project Health Dashboard

Fire all checks in parallel. Assemble a single status report at the end.

---

## Step 1 — Run all checks simultaneously

Launch every check at once — they are fully independent:

**Git state:**
```bash
git status --short && echo "---" && git log --oneline -5
```

**CI — last runs:**
```bash
gh run list --limit=5 --json status,conclusion,name,createdAt,databaseId \
  --jq '.[] | "\(.name) | \(.status) | \(.conclusion // "in_progress") | \(.createdAt)"'
```

**Server health:**
```bash
SERVER_IP=$(tailscale status --json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    peers=[v for v in d.get('Peer',{}).values() if 'garmincoach' in v.get('HostName','').lower()]; \
    print(peers[0]['TailscaleIPs'][0] if peers else '')" 2>/dev/null)
if [ -n "$SERVER_IP" ]; then
  curl -sf --max-time 5 "http://${SERVER_IP}:8765/health" && echo "✅ Server healthy" || echo "❌ Server unreachable"
else
  echo "⚠️  Could not resolve garmincoach-server Tailscale IP"
fi
```

**Today's Garmin snapshot:**
```bash
export PATH="$HOME/.local/bin:$PATH"
uv run garmin-connect training readiness 2>/dev/null || echo "Readiness: unavailable"
```

**Current training plan:**
```bash
cat ~/.config/garmin-connect-cli/training_plan.json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    print(f'Phase {d[\"phase\"]}: {d[\"phase_name\"]} | Week {d[\"week_start\"]} – {d[\"week_end\"]}'); \
    [print(f'  {s[\"date\"]} {s[\"day\"]}: {s[\"type\"]} ({\"✅\" if s[\"completed\"] else \"⬜\"})')  \
    for s in d.get('sessions',[])]" 2>/dev/null || echo "No training plan on file"
```

---

## Step 2 — Assemble the report

Format a concise status board:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT STATUS  [timestamp]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GIT
  Branch: main | <N> uncommitted changes
  Last: <sha> <subject>

CI (last 5 runs)
  ✅ Test        | completed | success
  ✅ Deploy Server| completed | success
  ...

SERVER
  ✅ garmincoach healthy | <IP>:8765
  (or ❌ unreachable)

GARMIN TODAY
  Readiness: <score> (<level>)
  HRV: <status>

TRAINING PLAN
  Phase <N>: <name> | <week range>
  <date> <day>: <type> ✅/⬜
  ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Flag anything that needs attention:
- Uncommitted changes with unrelated edits
- CI failures in the last 3 runs
- Server unreachable
- Plan sessions overdue (date < today, completed = false)

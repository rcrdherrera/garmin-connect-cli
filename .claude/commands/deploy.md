---
description: Run local checks, push to main, and watch CI + server deploy
allowed-tools: [Bash]
---

# /deploy — Push and Deploy

Gate → push → watch CI → verify server. Abort at any failure.

---

## Step 1 — Local gate

Run lint and tests first. If this fails, stop — do not push.

```bash
export PATH="$HOME/.local/bin:$PATH" && make can-release
```

If it fails: surface the error output and tell the user what broke. Do not proceed.

---

## Step 2 — Push

```bash
git push origin main
```

---

## Step 3 — Watch CI

Get the run ID for the Test workflow that just triggered, then tail it live:

```bash
sleep 3
gh run list --workflow=test.yml --limit=1
```

Then watch it to completion:

```bash
gh run watch $(gh run list --workflow=test.yml --limit=1 --json databaseId --jq '.[0].databaseId')
```

If Test fails: show the failed step output and stop — the server deploy will not trigger.

---

## Step 4 — Watch server deploy

The Deploy Server workflow triggers automatically when Test succeeds. Watch it:

```bash
sleep 5
gh run watch $(gh run list --workflow=deploy-server.yml --limit=1 --json databaseId --jq '.[0].databaseId')
```

If it fails: show the runner logs.

---

## Step 5 — Health probe

Wait a few seconds for the service to fully come up, then probe the API directly:

```bash
sleep 5
SERVER_IP=$(tailscale status --json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    peers=[v for v in d.get('Peer',{}).values() if 'garmincoach' in v.get('HostName','').lower()]; \
    print(peers[0]['TailscaleIPs'][0] if peers else '')" 2>/dev/null)
if [ -n "$SERVER_IP" ]; then
  curl -sf --max-time 5 "http://${SERVER_IP}:8765/health" \
    && echo "✅ /health responded — server is live" \
    || echo "❌ /health unreachable — service may still be starting"
else
  echo "⚠️  Could not resolve garmincoach-server Tailscale IP — skipping health probe"
fi
```

---

## Step 6 — Report

Report to the user:
- Which commit was deployed (git short SHA + subject)
- Total time from push to live
- Health probe result
- Whether any step required attention

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
make can-release
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

## Step 5 — Verify

Check that the service restarted on the self-hosted runner. The deploy workflow already calls
`systemctl is-active garmincoach` — if Step 4 succeeded, the service is up.

Report to the user:
- Which commit was deployed (git short SHA + subject)
- Total time from push to live
- Whether any step required attention

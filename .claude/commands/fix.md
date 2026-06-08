---
description: Run make can-release, diagnose failures, auto-fix, repeat until green
allowed-tools: [Bash, Read, Edit]
---

# /fix — Self-Healing Loop

Run the full CI check suite locally, diagnose any failures, apply fixes, and re-run until
green or until 3 attempts are exhausted. Surface a clear diagnosis if still broken after 3 tries.

---

## Step 1 — Run make can-release

```bash
export PATH="$HOME/.local/bin:$PATH"
make can-release 2>&1
```

If it passes on the first run: report green and stop. Nothing to fix.

---

## Step 2 — Diagnose the failure

Read the output carefully and categorize the failure:

| Category | Indicators | Fix strategy |
|----------|-----------|--------------|
| **Format** | `ruff format --check` diff output | `make fmt` auto-fixes this completely |
| **Lint** | `ruff check` rule violations (e.g. `F401`, `E501`) | `make fmt` fixes most; others need manual edit |
| **Import error** | `ModuleNotFoundError`, `ImportError` at test collection | Check pyproject.toml dependencies; run `make install` |
| **Syntax error** | `SyntaxError` in a specific file | Fix the syntax at the reported line |
| **Test assertion** | `AssertionError`, `assert X == Y` | Fix the code logic or update the test if the behavior is intentionally changed |
| **Test collection** | `ERROR collecting tests/...` | Usually a missing fixture or bad import |
| **Type/attr error** | `AttributeError`, `TypeError` at runtime in test | Fix the implementation |

---

## Step 3 — Apply the fix

### For format/lint errors
```bash
export PATH="$HOME/.local/bin:$PATH"
make fmt 2>&1
```
This resolves ~90% of ruff issues. Re-run after.

### For everything else
Read the failing file, fix the specific error, then re-run Step 1.

**Rules:**
- Fix only what's reported — don't refactor surrounding code.
- If a test assertion fails and the new behavior is correct, update the test. If the test reveals a real bug, fix the implementation.
- If an import is missing from pyproject.toml, add it, then run `make install` before re-running.

---

## Step 4 — Re-run (up to 3 attempts total)

After each fix, repeat Step 1. Count attempts.

- **Attempt 1 failed, attempt 2 green**: report what was fixed.
- **3 attempts all failed**: stop fixing. Report:
  1. The exact error output from the last run
  2. What you tried and why it didn't work
  3. What human action is likely needed (e.g. missing env var, upstream API change, schema mismatch)

---

## Notes

- `make can-release` runs lint first, then tests. Fix lint before debugging test failures — a lint error can mask real test output.
- `uv` must be on PATH. If `make` fails with `uv: command not found`, prepend `export PATH="$HOME/.local/bin:$PATH"` to the command.
- `server.py` is not tested by `make test` — that only covers `src/garmin_connect_cli/`. Server issues must be caught via `/deploy` + `/status`.

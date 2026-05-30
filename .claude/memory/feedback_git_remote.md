---
name: feedback-git-remote
description: "Always push garmin-connect-cli to the personal fork, not origin"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3a9c91d6-2b9c-4288-bdd9-9bbfb38fba86
---

Always push `garmin-connect-cli` to the `personal` remote, never `origin`.

**Why:** `origin` points to the upstream repo (`eddmann/garmin-connect-cli`) which Ricardo does not have push access to. His fork is at `rcrdherrera/garmin-connect-cli`, tracked as the `personal` remote.

**How to apply:** Use `git push personal main` (not `git push`) whenever pushing from `C:\garmin-connect-cli`. The Garmin-Coach repo (`c:\Users\ricar\Github\Garmin-Coach`) is fine with `git push` as usual.

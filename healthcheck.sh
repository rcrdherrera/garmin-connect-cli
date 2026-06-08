#!/usr/bin/env bash
# GarminCoach HTTP health check — run by garmincoach-healthcheck.timer
# Curls localhost:8765/health; pushes ntfy.sh notification if down.
# Requires NTFY_TOPIC in /etc/garmincoach.env

set -euo pipefail

PORT="${COACH_PORT:-8765}"
URL="http://localhost:${PORT}/health"
TIMEOUT=5
HOST=$(hostname -s)

if curl -sf --max-time "$TIMEOUT" "$URL" > /dev/null 2>&1; then
  exit 0
fi

# Server did not respond — send push notification
if [ -n "${NTFY_TOPIC:-}" ]; then
  curl -s --max-time 5 \
    -H "Title: GarminCoach DOWN on ${HOST}" \
    -H "Priority: high" \
    -H "Tags: rotating_light" \
    -d "Health check failed: ${URL} did not respond within ${TIMEOUT}s" \
    "https://ntfy.sh/${NTFY_TOPIC}" || true
fi

exit 1

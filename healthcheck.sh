#!/usr/bin/env bash
# GarminCoach HTTP health check — run by garmincoach-healthcheck.timer
# Curls localhost:8765/health; sends a Telegram message if down.
# Requires TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in /etc/garmincoach.env

set -euo pipefail

PORT="${COACH_PORT:-8765}"
URL="http://localhost:${PORT}/health"
TIMEOUT=5
HOST=$(hostname -s)

if curl -sf --max-time "$TIMEOUT" "$URL" > /dev/null 2>&1; then
  exit 0
fi

# Server did not respond — send Telegram alert
if [ -n "${TELEGRAM_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  curl -s --max-time 5 \
    "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    -d "text=🚨 GarminCoach DOWN on ${HOST}%0A${URL} did not respond within ${TIMEOUT}s" \
    > /dev/null || true
fi

exit 1

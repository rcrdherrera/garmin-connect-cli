#!/usr/bin/env bash
# Run ONCE on the Ubuntu server to install the hourly health check timer.
# Usage: sudo bash setup_healthcheck.sh <ntfy-topic>
#
# After setup, subscribe to https://ntfy.sh/<ntfy-topic> in the ntfy app
# to receive push notifications when the server goes down.

set -euo pipefail

NTFY_TOPIC="${1:-}"
if [ -z "$NTFY_TOPIC" ]; then
  echo "Usage: sudo bash setup_healthcheck.sh <ntfy-topic>"
  echo "  Example: sudo bash setup_healthcheck.sh garmincoach-abc123"
  exit 1
fi

REPO_DIR=/opt/garmin-connect-cli

echo "→ Adding NTFY_TOPIC to /etc/garmincoach.env"
if grep -q '^NTFY_TOPIC=' /etc/garmincoach.env 2>/dev/null; then
  sed -i "s|^NTFY_TOPIC=.*|NTFY_TOPIC=${NTFY_TOPIC}|" /etc/garmincoach.env
else
  echo "NTFY_TOPIC=${NTFY_TOPIC}" >> /etc/garmincoach.env
fi

echo "→ Installing healthcheck.sh"
cp "${REPO_DIR}/healthcheck.sh" /opt/garmin-connect-cli/healthcheck.sh
chmod +x /opt/garmin-connect-cli/healthcheck.sh

echo "→ Installing systemd units"
cp "${REPO_DIR}/garmincoach-healthcheck.service" /etc/systemd/system/
cp "${REPO_DIR}/garmincoach-healthcheck.timer"   /etc/systemd/system/

echo "→ Enabling and starting timer"
systemctl daemon-reload
systemctl enable --now garmincoach-healthcheck.timer

echo ""
echo "✅ Health check installed."
echo "   Timer fires 2 min after boot, then every hour."
echo "   Subscribe to push notifications: https://ntfy.sh/${NTFY_TOPIC}"
echo "   Test now: sudo systemctl start garmincoach-healthcheck.service"

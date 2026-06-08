#!/usr/bin/env bash
# Daily health check for garmincoach server over Tailscale.
# Installed as a macOS LaunchAgent — runs on your Mac where Tailscale is available.
# Sends a native macOS notification if the server is unreachable.

set -euo pipefail

PORT=8765
TIMEOUT=5

# Resolve garmincoach-server Tailscale IP dynamically
SERVER_IP=$(tailscale status --json 2>/dev/null \
  | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    peers = [v for v in d.get('Peer', {}).values()
             if 'garmincoach' in v.get('HostName', '').lower()]
    print(peers[0]['TailscaleIPs'][0] if peers else '')
except Exception:
    print('')
" 2>/dev/null)

if [ -z "$SERVER_IP" ]; then
  osascript -e 'display notification "Could not resolve garmincoach-server on Tailscale — is Tailscale running?" with title "GarminCoach Health Check" subtitle "⚠️ Tailscale issue"'
  exit 1
fi

URL="http://${SERVER_IP}:${PORT}/health"

if curl -sf --max-time "$TIMEOUT" "$URL" > /dev/null 2>&1; then
  # Healthy — silent
  exit 0
else
  osascript -e "display notification \"${URL} did not respond within ${TIMEOUT}s\" with title \"GarminCoach Health Check\" subtitle \"❌ Server is DOWN\""
  exit 1
fi

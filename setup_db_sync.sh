#!/usr/bin/env bash
# Set up a daily systemd timer to sync Garmin data into garmin.db.
# Run once on the server (as root or with sudo):
#   bash setup_db_sync.sh
#
# After setup, trigger the first sync manually:
#   sudo systemctl start garmin-db-sync.service

set -euo pipefail

INSTALL_DIR="/opt/garmin-connect-cli"
SERVICE_USER="ricardo"

# ── garmin-db-sync.service ────────────────────────────────────────────────────
cat > /etc/systemd/system/garmin-db-sync.service << EOF
[Unit]
Description=Garmin DB incremental sync
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/garmin_db.py sync
StandardOutput=journal
StandardError=journal
EOF

# ── garmin-db-sync.timer ──────────────────────────────────────────────────────
cat > /etc/systemd/system/garmin-db-sync.timer << EOF
[Unit]
Description=Run Garmin DB sync daily at 06:00

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable garmin-db-sync.timer
systemctl start garmin-db-sync.timer

echo "Timer installed. Running first sync now..."
systemctl start garmin-db-sync.service

echo ""
echo "Done. Check progress with:"
echo "  journalctl -u garmin-db-sync -f"

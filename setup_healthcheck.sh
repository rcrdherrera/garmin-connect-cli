#!/usr/bin/env bash
# Run ONCE on the Ubuntu server to install the hourly health check timer.
#
# Prerequisites — create a Telegram bot first:
#   1. Message @BotFather on Telegram → /newbot → follow prompts → copy the token
#   2. Send any message to your new bot
#   3. Get your chat ID:
#      curl "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool
#      Look for: result[0].message.chat.id
#
# Usage:
#   sudo bash setup_healthcheck.sh <telegram-bot-token> <telegram-chat-id>
#
# Example:
#   sudo bash setup_healthcheck.sh 7812345678:AAFxyz... 123456789

set -euo pipefail

TELEGRAM_TOKEN="${1:-}"
TELEGRAM_CHAT_ID="${2:-}"

if [ -z "$TELEGRAM_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
  echo "Usage: sudo bash setup_healthcheck.sh <telegram-bot-token> <telegram-chat-id>"
  echo ""
  echo "To get these values:"
  echo "  1. Message @BotFather on Telegram → /newbot → copy the token"
  echo "  2. Send any message to your bot"
  echo "  3. Run: curl \"https://api.telegram.org/bot<TOKEN>/getUpdates\""
  echo "     Look for result[0].message.chat.id"
  exit 1
fi

REPO_DIR=/opt/garmin-connect-cli
ENV_FILE=/etc/garmincoach.env

echo "→ Writing Telegram credentials to ${ENV_FILE}"
for key in TELEGRAM_TOKEN TELEGRAM_CHAT_ID; do
  val="${!key}"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
done

echo "→ Installing healthcheck.sh"
chmod +x "${REPO_DIR}/healthcheck.sh"

echo "→ Installing systemd units"
cp "${REPO_DIR}/garmincoach-healthcheck.service" /etc/systemd/system/
cp "${REPO_DIR}/garmincoach-healthcheck.timer"   /etc/systemd/system/

echo "→ Enabling and starting timer"
systemctl daemon-reload
systemctl enable --now garmincoach-healthcheck.timer

echo ""
echo "✅ Health check installed. Timer fires 2 min after boot, then every hour."
echo ""
echo "Test it now:"
echo "  sudo systemctl start garmincoach-healthcheck.service"
echo "  journalctl -u garmincoach-healthcheck.service -n 20"

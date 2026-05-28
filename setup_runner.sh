#!/usr/bin/env bash
# Install and register a GitHub Actions self-hosted runner for garmincoach.
#
# Run on the Ubuntu server:
#   bash setup_runner.sh <RUNNER_TOKEN>
#
# Get the token from:
#   https://github.com/rcrdherrera/garmin-connect-cli/settings/actions/runners/new
#   (click "New self-hosted runner", copy the token shown in the configure step)

set -euo pipefail

RUNNER_TOKEN="${1:?Usage: $0 <RUNNER_TOKEN>}"
REPO_URL="https://github.com/rcrdherrera/garmin-connect-cli"
RUNNER_VERSION="2.325.0"
RUNNER_DIR="/opt/actions-runner"
RUNNER_USER="${SUDO_USER:-$USER}"

# ── 1. Download runner ────────────────────────────────────────────────────────
echo "==> Creating runner directory: $RUNNER_DIR"
sudo mkdir -p "$RUNNER_DIR"
sudo chown "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR"

cd "$RUNNER_DIR"

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  RUNNER_ARCH="x64" ;;
    aarch64) RUNNER_ARCH="arm64" ;;
    *)       echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

TARBALL="actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
echo "==> Downloading runner v${RUNNER_VERSION} (${RUNNER_ARCH})..."
curl -fsSL -o "$TARBALL" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"
tar xzf "$TARBALL"
rm "$TARBALL"

# ── 2. Configure runner ───────────────────────────────────────────────────────
echo "==> Configuring runner..."
./config.sh \
    --url "$REPO_URL" \
    --token "$RUNNER_TOKEN" \
    --name "garmincoach-server" \
    --labels "self-hosted,Linux,garmincoach" \
    --work "_work" \
    --unattended \
    --replace

# ── 3. Install as systemd service ─────────────────────────────────────────────
echo "==> Installing runner as systemd service..."
sudo ./svc.sh install "$RUNNER_USER"
sudo ./svc.sh start

# ── 4. Sudoers: allow runner to restart garmincoach without password ───────────
SUDOERS_FILE="/etc/sudoers.d/garmincoach-runner"
echo "==> Adding sudoers rule for systemctl restart garmincoach..."
echo "$RUNNER_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart garmincoach" \
    | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 440 "$SUDOERS_FILE"

# ── 5. Verify ─────────────────────────────────────────────────────────────────
echo ""
echo "==> Runner service status:"
sudo ./svc.sh status

echo ""
echo "Done. Runner is registered and running."
echo "Push any commit to main to trigger a deploy."

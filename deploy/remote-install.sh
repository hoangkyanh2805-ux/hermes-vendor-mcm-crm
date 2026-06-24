#!/bin/bash
# One-line remote install (run on VPS via VNC if SSH blocked):
#   curl -fsSL https://raw.githubusercontent.com/hoangkyanh2805-ux/hermes-vendor-mcm-crm/master/deploy/remote-install.sh | bash
set -euo pipefail

APP_DOMAIN="${APP_DOMAIN:-agent.tiemhoatmon.com}"
REMOTE_DIR="/opt/hermes-vendor-mcm-crm"
REPO="https://github.com/hoangkyanh2805-ux/hermes-vendor-mcm-crm.git"

echo "=== Remote install Hermes Growth OS ==="

# Firewall: open 80/443 for Caddy + Telegram webhook
if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-service=http 2>/dev/null || true
  firewall-cmd --permanent --add-service=https 2>/dev/null || true
  firewall-cmd --permanent --add-port=3000/tcp 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
fi

grep -q '8.8.8.8' /etc/resolv.conf 2>/dev/null || echo 'nameserver 8.8.8.8' >> /etc/resolv.conf

if [ -d "$REMOTE_DIR/.git" ]; then
  cd "$REMOTE_DIR" && git pull --ff-only
else
  rm -rf "$REMOTE_DIR"
  git clone "$REPO" "$REMOTE_DIR"
fi

if [ ! -f "$REMOTE_DIR/.env" ]; then
  echo "ERROR: Create $REMOTE_DIR/.env first (copy from local machine)"
  exit 1
fi

bash "$REMOTE_DIR/deploy/vps-bootstrap.sh"

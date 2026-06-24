#!/bin/bash
# Run ON VPS as root — VNC or: ssh -p 2018 root@103.97.126.28
# Domain: agent.tiemhoatmon.com
set -euo pipefail

APP_DOMAIN="agent.tiemhoatmon.com"
REMOTE_DIR="/opt/hermes-vendor-mcm-crm"
WEBHOOK_SECRET="${HERMES_WEBHOOK_SECRET:-zIV8O-pGutzDkhjIzqIHhIfhez1q89Xr}"

echo "=== Hermes deploy: ${APP_DOMAIN} ==="

if [ ! -d "$REMOTE_DIR" ]; then
  echo "Missing $REMOTE_DIR — run initial upload first or git clone"
  exit 1
fi

grep -q '8.8.8.8' /etc/resolv.conf 2>/dev/null || echo 'nameserver 8.8.8.8' >> /etc/resolv.conf
dnf -y install python3 python3-pip python3-devel gcc postgresql-devel 2>/dev/null || \
  yum -y install python3 python3-pip python3-devel gcc postgresql-devel

cd "$REMOTE_DIR"
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt

# .env
sed -i "s|^APP_BASE_URL=.*|APP_BASE_URL=https://${APP_DOMAIN}|" .env
sed -i "s|^METABASE_URL=.*|METABASE_URL=https://${APP_DOMAIN}/metabase|" .env
grep -q '^HERMES_WEBHOOK_SECRET=' .env || echo "HERMES_WEBHOOK_SECRET=${WEBHOOK_SECRET}" >> .env
grep -q '^WEBHOOK_PORT=' .env || echo 'WEBHOOK_PORT=8080' >> .env

# Caddy
mkdir -p /etc/caddy
cat > /etc/caddy/Caddyfile << EOF
${APP_DOMAIN} {
    handle /webhook/* {
        reverse_proxy 127.0.0.1:8080
    }
    handle /health {
        reverse_proxy 127.0.0.1:8080
    }
    handle /metabase/* {
        uri strip_prefix /metabase
        reverse_proxy 127.0.0.1:3000
    }
    handle {
        respond "Hermes Growth OS OK" 200
    }
}
EOF
systemctl enable caddy
systemctl restart caddy

# Webhook service
cat > /etc/systemd/system/hermes-webhook.service << EOF
[Unit]
Description=Hermes Telegram Webhook
After=network.target

[Service]
Type=simple
WorkingDirectory=${REMOTE_DIR}
EnvironmentFile=${REMOTE_DIR}/.env
ExecStart=${REMOTE_DIR}/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8080 --timeout 120 telegram_webhook_server:app --chdir ${REMOTE_DIR}/scripts
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now hermes-webhook

# Metabase
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker compose up -d metabase 2>/dev/null || true

sleep 4
echo "--- health local ---"
curl -sf http://127.0.0.1:8080/health && echo ""
echo "--- health public ---"
curl -sf "https://${APP_DOMAIN}/health" && echo ""

set -a && source .env && set +a
WH_URL="https://${APP_DOMAIN}/webhook/telegram/${HERMES_WEBHOOK_SECRET}"
curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${WH_URL}" -d "drop_pending_updates=true" && echo ""
curl -sf "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" && echo ""

echo ""
echo "DONE"
echo "  Health:   https://${APP_DOMAIN}/health"
echo "  Metabase: https://${APP_DOMAIN}/metabase"
echo "  Bot test: https://t.me/hermes_vendor_mcm_crm_bot?start=src_xacc_uae_001_uae_goldhook_20260624"

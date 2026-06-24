#!/usr/bin/env python3
"""Fix VPS deploy: native Python webhook + Metabase docker + Caddy."""
from __future__ import annotations

import paramiko

VPS_HOST = "103.97.126.28"
VPS_PORT = 2018
VPS_USER = "root"
VPS_PASS = "x8Bz4MZGvz"
APP_DOMAIN = "103-97-126-28.sslip.io"
REMOTE_DIR = "/opt/hermes-vendor-mcm-crm"


def run(ssh, cmd, timeout=600):
    print(f"\n>>> {cmd[:150]}")
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    c = o.channel.recv_exit_status()
    out, err = o.read().decode(errors="replace"), e.read().decode(errors="replace")
    if out.strip():
        print(out[-2500:])
    if err.strip() and c != 0:
        print("ERR:", err[-1000:])
    return c, out


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS, timeout=45)

    cmds = [
        # DNS fix for docker + apt
        "grep -q '8.8.8.8' /etc/resolv.conf || echo 'nameserver 8.8.8.8' >> /etc/resolv.conf",
        "grep -q '1.1.1.1' /etc/resolv.conf || echo 'nameserver 1.1.1.1' >> /etc/resolv.conf",
        "dnf -y install python3 python3-pip python3-devel postgresql-devel gcc 2>/dev/null || yum -y install python3 python3-pip python3-devel postgresql-devel gcc",
        f"cd {REMOTE_DIR} && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt",
        "mkdir -p /etc/caddy",
        f"""cat > /etc/caddy/Caddyfile << 'EOF'
{APP_DOMAIN} {{
    handle /webhook/* {{
        reverse_proxy 127.0.0.1:8080
    }}
    handle /health {{
        reverse_proxy 127.0.0.1:8080
    }}
    handle /metabase/* {{
        uri strip_prefix /metabase
        reverse_proxy 127.0.0.1:3000
    }}
    handle {{
        respond "Hermes Growth OS OK" 200
    }}
}}
EOF""",
        "systemctl enable caddy && systemctl restart caddy",
        f"""cat > /etc/systemd/system/hermes-webhook.service << 'EOF'
[Unit]
Description=Hermes Telegram Webhook
After=network.target

[Service]
Type=simple
WorkingDirectory={REMOTE_DIR}
EnvironmentFile={REMOTE_DIR}/.env
ExecStart={REMOTE_DIR}/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8080 --timeout 120 telegram_webhook_server:app --chdir {REMOTE_DIR}/scripts
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF""",
        "systemctl daemon-reload",
        "systemctl enable --now hermes-webhook",
        f"cd {REMOTE_DIR} && docker compose up -d metabase",
        "sleep 5 && curl -sf http://127.0.0.1:8080/health",
        f"cd {REMOTE_DIR} && set -a && source .env && set +a && curl -sf 'https://api.telegram.org/bot'$TELEGRAM_BOT_TOKEN'/getWebhookInfo'",
        f"curl -sf https://{APP_DOMAIN}/health || curl -sk https://{APP_DOMAIN}/health",
    ]
    for c in cmds:
        run(ssh, c, timeout=1200)
    ssh.close()
    print("\nFix complete.")


if __name__ == "__main__":
    main()

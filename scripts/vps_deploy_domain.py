#!/usr/bin/env python3
"""Configure agent.tiemhoatmon.com on VPS."""
from __future__ import annotations

import paramiko

VPS_HOST = "103.97.126.28"
VPS_PORT = 2018
VPS_USER = "root"
VPS_PASS = "x8Bz4MZGvz"
APP_DOMAIN = "agent.tiemhoatmon.com"
APP_BASE_URL = f"https://{APP_DOMAIN}"
REMOTE_DIR = "/opt/hermes-vendor-mcm-crm"
WEBHOOK_SECRET = "zIV8O-pGutzDkhjIzqIHhIfhez1q89Xr"


def run(ssh, cmd, timeout=600):
    print(f"\n>>> {cmd[:160]}")
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    c = o.channel.recv_exit_status()
    out, err = o.read().decode(errors="replace"), e.read().decode(errors="replace")
    if out.strip():
        print(out[-3000:])
    if err.strip() and c != 0:
        print("ERR:", err[-1200:])
    return c, out


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"SSH {VPS_HOST}:{VPS_PORT}...")
    ssh.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS, timeout=90)

    env_patch = f"""
cd {REMOTE_DIR} && \\
sed -i 's|^APP_BASE_URL=.*|APP_BASE_URL={APP_BASE_URL}|' .env && \\
sed -i 's|^METABASE_URL=.*|METABASE_URL={APP_BASE_URL}/metabase|' .env && \\
grep -q '^WEBHOOK_PORT=' .env || echo 'WEBHOOK_PORT=8080' >> .env
"""

    caddy = f"""{APP_DOMAIN} {{
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
"""

    steps = [
        f"test -d {REMOTE_DIR} || (echo MISSING {REMOTE_DIR} && exit 1)",
        "grep -q '8.8.8.8' /etc/resolv.conf 2>/dev/null || echo 'nameserver 8.8.8.8' >> /etc/resolv.conf",
        "dnf -y install python3 python3-pip python3-devel gcc postgresql-devel 2>/dev/null || yum -y install python3 python3-pip python3-devel gcc postgresql-devel",
        f"cd {REMOTE_DIR} && (test -d .venv || python3 -m venv .venv) && .venv/bin/pip install -q -r requirements.txt",
        env_patch,
        f"mkdir -p /etc/caddy && cat > /etc/caddy/Caddyfile << 'EOF'\n{caddy}\nEOF",
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
        "systemctl enable hermes-webhook",
        "systemctl restart hermes-webhook",
        f"cd {REMOTE_DIR} && docker compose up -d metabase 2>/dev/null || true",
        "sleep 3 && curl -sf http://127.0.0.1:8080/health",
        f"cd {REMOTE_DIR} && set -a && source .env && set +a && curl -sf -X POST https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook -d url={APP_BASE_URL}/webhook/telegram/{WEBHOOK_SECRET} -d drop_pending_updates=true",
        f"cd {REMOTE_DIR} && set -a && source .env && set +a && curl -sf https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo",
        f"curl -sf https://{APP_DOMAIN}/health || curl -sk https://{APP_DOMAIN}/health",
        "systemctl is-active hermes-webhook caddy",
    ]
    for s in steps:
        run(ssh, s, timeout=1200)
    ssh.close()
    print("\n=== DONE ===")
    print(f"Health:   {APP_BASE_URL}/health")
    print(f"Metabase: {APP_BASE_URL}/metabase")
    print(f"Webhook:  {APP_BASE_URL}/webhook/telegram/{WEBHOOK_SECRET}")


if __name__ == "__main__":
    main()

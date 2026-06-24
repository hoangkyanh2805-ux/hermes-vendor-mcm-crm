#!/usr/bin/env python3
"""Full auto deploy to VPS — agent.tiemhoatmon.com"""
from __future__ import annotations

import io
import secrets
import sys
import tarfile
import time
from pathlib import Path

import paramiko

VPS_HOST = "103.97.126.28"
VPS_PORT = 2018
VPS_USER = "root"
VPS_PASS = "x8Bz4MZGvz"
APP_DOMAIN = "agent.tiemhoatmon.com"
APP_BASE_URL = f"https://{APP_DOMAIN}"
REMOTE_DIR = "/opt/hermes-vendor-mcm-crm"
ROOT = Path(__file__).resolve().parent.parent
ENV_LOCAL = ROOT / ".env"
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".cursor"}
SKIP_FILES = {".env"}
WEBHOOK_SECRET = "zIV8O-pGutzDkhjIzqIHhIfhez1q89Xr"


def run(ssh, cmd, timeout=900):
    print(f"\n>>> {cmd[:150]}")
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    c = o.channel.recv_exit_status()
    out, err = o.read().decode(errors="replace"), e.read().decode(errors="replace")
    if out.strip():
        print(out[-3500:])
    if err.strip() and c != 0:
        print("ERR:", err[-1500:])
    return c, out


def build_env() -> str:
    text = ENV_LOCAL.read_text(encoding="utf-8")
    overrides = {
        "APP_BASE_URL": APP_BASE_URL,
        "METABASE_URL": f"{APP_BASE_URL}/metabase",
        "HERMES_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "WEBHOOK_PORT": "8080",
        "METABASE_PORT": "3000",
        "NODE_ENV": "production",
    }
    lines, seen = [], set()
    for line in text.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in overrides:
                lines.append(f"{k}={overrides[k]}")
                seen.add(k)
                continue
        lines.append(line)
    for k, v in overrides.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    return "\n".join(lines) + "\n"


def make_tar() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT)
            if any(p in SKIP_DIRS for p in rel.parts) or rel.name in SKIP_FILES:
                continue
            if path.is_file():
                tar.add(path, arcname=str(rel).replace("\\", "/"))
    buf.seek(0)
    return buf.read()


def connect() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for attempt in range(5):
        try:
            print(f"SSH attempt {attempt + 1} -> {VPS_HOST}:{VPS_PORT}")
            ssh.connect(
                VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS,
                timeout=120, banner_timeout=120, auth_timeout=120,
            )
            return ssh
        except Exception as exc:
            print(f"  failed: {exc}")
            time.sleep(8)
    raise SystemExit("Cannot SSH to VPS after 5 attempts")


def main() -> int:
    ssh = connect()

    run(ssh, "hostname && whoami")
    run(ssh, "grep -q '8.8.8.8' /etc/resolv.conf 2>/dev/null || echo 'nameserver 8.8.8.8' >> /etc/resolv.conf")
    run(ssh, "dnf -y install python3 python3-pip python3-devel gcc postgresql-devel tar gzip 2>/dev/null || yum -y install python3 python3-pip python3-devel gcc postgresql-devel tar gzip")
    run(ssh, "command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh")
    run(ssh, "systemctl enable --now docker")
    run(ssh, f"mkdir -p {REMOTE_DIR}")

    print("Uploading project...")
    sftp = ssh.open_sftp()
    sftp.file("/tmp/hermes.tar.gz", "wb").write(make_tar())
    sftp.file(f"{REMOTE_DIR}/.env", "w").write(build_env())
    sftp.close()
    run(ssh, f"tar -xzf /tmp/hermes.tar.gz -C {REMOTE_DIR}")

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
    run(ssh, "command -v caddy >/dev/null || (dnf -y install 'dnf-command(copr)' && dnf -y copr enable @caddy/caddy && dnf -y install caddy)")
    run(ssh, f"mkdir -p /etc/caddy && cat > /etc/caddy/Caddyfile << 'EOF'\n{caddy}\nEOF")
    run(ssh, "systemctl enable caddy && systemctl restart caddy")

    run(ssh, f"cd {REMOTE_DIR} && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt", timeout=1200)

    unit = f"""[Unit]
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
"""
    run(ssh, f"cat > /etc/systemd/system/hermes-webhook.service << 'EOF'\n{unit}\nEOF")
    run(ssh, "systemctl daemon-reload && systemctl enable --now hermes-webhook")

    run(ssh, f"cd {REMOTE_DIR} && docker compose up -d metabase", timeout=600)

    for i in range(20):
        _, out, = run(ssh, "curl -sf http://127.0.0.1:8080/health 2>/dev/null || true")
        if '"ok"' in out:
            print("Webhook healthy")
            break
        time.sleep(3)

    wh = f"{APP_BASE_URL}/webhook/telegram/{WEBHOOK_SECRET}"
    run(ssh, f"cd {REMOTE_DIR} && set -a && source .env && set +a && curl -sf -X POST https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook -d url={wh} -d drop_pending_updates=true")
    run(ssh, f"cd {REMOTE_DIR} && set -a && source .env && set +a && curl -sf https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo")
    run(ssh, f"curl -sf https://{APP_DOMAIN}/health || curl -sk https://{APP_DOMAIN}/health")
    run(ssh, "systemctl is-active hermes-webhook caddy && docker ps --format '{{.Names}} {{.Status}}'")

    ssh.close()
    ENV_LOCAL.write_text(build_env(), encoding="utf-8")
    print("\n=== ALL DONE ===")
    print(f"Health:   {APP_BASE_URL}/health")
    print(f"Metabase: {APP_BASE_URL}/metabase")
    print(f"Webhook:  {wh}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

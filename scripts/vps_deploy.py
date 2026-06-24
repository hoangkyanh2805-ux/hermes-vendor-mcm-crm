#!/usr/bin/env python3
"""One-shot VPS deploy: Hermes webhook + Metabase + Caddy."""
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
APP_DOMAIN = "103-97-126-28.sslip.io"
APP_BASE_URL = f"https://{APP_DOMAIN}"
REMOTE_DIR = "/opt/hermes-vendor-mcm-crm"

ROOT = Path(__file__).resolve().parent.parent
ENV_LOCAL = ROOT / ".env"
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".cursor"}
SKIP_FILES = {".env"}


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 900) -> tuple[int, str, str]:
    print(f"\n>>> {cmd[:140]}")
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if out.strip():
        tail = out[-4000:] if len(out) > 4000 else out
        print(tail)
    if err.strip() and code != 0:
        print("STDERR:", err[-1500:])
    return code, out, err


def build_env(webhook_secret: str) -> str:
    local = ENV_LOCAL.read_text(encoding="utf-8")
    lines: list[str] = []
    extras = {
        "APP_BASE_URL": APP_BASE_URL,
        "HERMES_WEBHOOK_SECRET": webhook_secret,
        "WEBHOOK_PORT": "8080",
        "METABASE_PORT": "3000",
        "METABASE_URL": f"{APP_BASE_URL}/metabase",
        "NODE_ENV": "production",
    }
    seen: set[str] = set()
    for line in local.splitlines():
        if "=" not in line or line.strip().startswith("#"):
            lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in extras:
            lines.append(f"{key}={extras[key]}")
            seen.add(key)
        else:
            lines.append(line)
    for k, v in extras.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    return "\n".join(lines) + "\n"


def make_project_tar() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT)
            if any(p in SKIP_DIRS for p in rel.parts):
                continue
            if rel.name in SKIP_FILES:
                continue
            if path.is_file():
                tar.add(path, arcname=str(rel).replace("\\", "/"))
    buf.seek(0)
    return buf.read()


def main() -> int:
    webhook_secret = secrets.token_urlsafe(24)
    env_content = build_env(webhook_secret)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {VPS_USER}@{VPS_HOST}:{VPS_PORT}...")
    ssh.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS, timeout=45)

    setup = [
        "dnf -y install git curl tar gzip firewalld 2>/dev/null || yum -y install git curl tar gzip firewalld",
        "systemctl enable --now firewalld 2>/dev/null || true",
        "firewall-cmd --permanent --add-service=http 2>/dev/null; firewall-cmd --permanent --add-service=https 2>/dev/null; firewall-cmd --permanent --add-port=3000/tcp 2>/dev/null; firewall-cmd --reload 2>/dev/null || true",
        "command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh",
        "systemctl enable --now docker",
        "docker compose version >/dev/null 2>&1 || (dnf -y install docker-compose-plugin 2>/dev/null || yum -y install docker-compose-plugin 2>/dev/null || true)",
        f"mkdir -p {REMOTE_DIR}",
    ]
    for c in setup:
        run(ssh, c)

    # Upload project tarball
    print("Uploading project...")
    tarball = make_project_tar()
    sftp = ssh.open_sftp()
    with sftp.file("/tmp/hermes-deploy.tar.gz", "wb") as f:
        f.write(tarball)
    with sftp.file(f"{REMOTE_DIR}/.env", "w") as f:
        f.write(env_content)
    sftp.close()
    run(ssh, f"rm -rf {REMOTE_DIR}/* && tar -xzf /tmp/hermes-deploy.tar.gz -C {REMOTE_DIR}")

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
    run(ssh, f"cat > /etc/caddy/Caddyfile << 'CADDYEOF'\n{caddy}\nCADDYEOF")
    run(ssh, "command -v caddy >/dev/null || (dnf -y install 'dnf-command(copr)' && dnf -y copr enable @caddy/caddy && dnf -y install caddy)")
    run(ssh, "systemctl enable caddy 2>/dev/null; systemctl restart caddy 2>/dev/null || (caddy run --config /etc/caddy/Caddyfile &)")

    run(ssh, f"cd {REMOTE_DIR} && docker compose build hermes-webhook", timeout=1200)
    run(ssh, f"cd {REMOTE_DIR} && docker compose up -d hermes-webhook metabase", timeout=300)

    for _ in range(15):
        _, out, _ = run(ssh, "curl -sf http://127.0.0.1:8080/health 2>/dev/null || true")
        if '"ok"' in out:
            break
        time.sleep(4)

    webhook_url = f"{APP_BASE_URL}/webhook/telegram/{webhook_secret}"
    run(
        ssh,
        f"cd {REMOTE_DIR} && source .env && curl -sf -X POST "
        f"'https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook' "
        f"-d 'url={webhook_url}' -d 'drop_pending_updates=true'",
    )
    run(
        ssh,
        f"cd {REMOTE_DIR} && source .env && curl -sf "
        f"'https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo'",
    )
    run(ssh, f"curl -sf https://{APP_DOMAIN}/health || curl -sk https://{APP_DOMAIN}/health")

    ssh.close()
    ENV_LOCAL.write_text(env_content, encoding="utf-8")

    print("\n=== DEPLOY DONE ===")
    print(f"Health:    {APP_BASE_URL}/health")
    print(f"Metabase:  {APP_BASE_URL}/metabase  (direct: http://{VPS_HOST}:3000)")
    print(f"Webhook:   {webhook_url}")
    print("Test bot:  https://t.me/hermes_vendor_mcm_crm_bot?start=src_xacc_uae_001_uae_goldhook_20260624")
    return 0


if __name__ == "__main__":
    sys.exit(main())

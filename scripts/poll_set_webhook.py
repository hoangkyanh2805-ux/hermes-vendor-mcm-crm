#!/usr/bin/env python3
"""
Poll public health URL; when up, register Telegram webhook.

Usage:
    python scripts/poll_set_webhook.py
    python scripts/poll_set_webhook.py --once
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False

load_dotenv()

APP_BASE_URL = os.getenv("APP_BASE_URL", "https://agent.tiemhoatmon.com").rstrip("/")
WEBHOOK_SECRET = os.getenv("HERMES_WEBHOOK_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
HEALTH_URL = f"{APP_BASE_URL}/health"


def check_health() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return data.get("status") == "ok"
    except Exception:
        return False


def set_webhook() -> dict:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    url = f"{APP_BASE_URL}/webhook/telegram/{WEBHOOK_SECRET}" if WEBHOOK_SECRET else f"{APP_BASE_URL}/webhook/telegram"
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    data = urllib.parse.urlencode({"url": url, "drop_pending_updates": "true"}).encode()
    req = urllib.request.Request(api, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_webhook_info() -> dict:
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo", timeout=15
    ) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()

    if args.once:
        ok = check_health()
        print(json.dumps({"health_url": HEALTH_URL, "healthy": ok}, indent=2))
        return 0 if ok else 1

    print(f"Waiting for {HEALTH_URL} ...")
    for i in range(120):
        if check_health():
            print("Health OK — registering webhook")
            result = set_webhook()
            info = get_webhook_info()
            print(json.dumps({"setWebhook": result, "getWebhookInfo": info}, indent=2))
            return 0
        print(f"  attempt {i + 1}: not ready, retry in {args.interval}s")
        time.sleep(args.interval)

    print("Timeout — run VNC install first: deploy/VNC-INSTALL.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())

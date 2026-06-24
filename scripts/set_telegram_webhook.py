#!/usr/bin/env python3
"""
Register Telegram bot webhook for Hermes capture.

Usage:
    python scripts/set_telegram_webhook.py info
    python scripts/set_telegram_webhook.py set
    python scripts/set_telegram_webhook.py set --url https://your-domain.com/webhook/telegram/SECRET
    python scripts/set_telegram_webhook.py delete
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("HERMES_WEBHOOK_SECRET", "")


def api(method: str, **params) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def build_webhook_url(override: str | None = None) -> str:
    if override:
        return override.rstrip("/")
    if not APP_BASE_URL:
        raise RuntimeError("Set APP_BASE_URL in .env or pass --url")
    secret = WEBHOOK_SECRET or "unset"
    if WEBHOOK_SECRET:
        return f"{APP_BASE_URL}/webhook/telegram/{WEBHOOK_SECRET}"
    return f"{APP_BASE_URL}/webhook/telegram"


def cmd_info() -> int:
    try:
        r = api("getWebhookInfo")
        print(json.dumps(r, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_set(url: str | None) -> int:
    try:
        webhook_url = build_webhook_url(url)
        r = api(
            "setWebhook",
            url=webhook_url,
            allowed_updates=json.dumps(["message", "edited_message"]),
            drop_pending_updates="true",
        )
        print(json.dumps({"webhook_url": webhook_url, "telegram": r}, indent=2))
        return 0 if r.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_delete() -> int:
    try:
        r = api("deleteWebhook", drop_pending_updates="true")
        print(json.dumps(r, indent=2))
        return 0 if r.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_gen_secret() -> int:
    print(secrets.token_urlsafe(32))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram webhook management")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="getWebhookInfo")
    set_p = sub.add_parser("set", help="setWebhook from APP_BASE_URL + HERMES_WEBHOOK_SECRET")
    set_p.add_argument("--url", help="Override full webhook URL")
    sub.add_parser("delete", help="deleteWebhook (switch to polling/dev)")
    sub.add_parser("gen-secret", help="Generate HERMES_WEBHOOK_SECRET")

    args = parser.parse_args()
    if args.command == "info":
        return cmd_info()
    if args.command == "set":
        return cmd_set(args.url)
    if args.command == "delete":
        return cmd_delete()
    if args.command == "gen-secret":
        return cmd_gen_secret()
    return 1


if __name__ == "__main__":
    sys.exit(main())

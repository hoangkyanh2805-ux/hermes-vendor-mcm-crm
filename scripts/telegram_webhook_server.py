#!/usr/bin/env python3
"""
Agent 1 — Telegram webhook server (Hermes capture bridge).

Receives Telegram updates via HTTPS webhook and runs capture_telegram_start().

Usage (dev):
    python scripts/telegram_webhook_server.py

Production:
    gunicorn -w 2 -b 0.0.0.0:8080 telegram_webhook_server:app --chdir scripts
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_a, **_k) -> bool:
        return False

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Import capture after dotenv
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_to_supabase import capture_telegram_start  # noqa: E402

try:
    from flask import Flask, jsonify, request
except ImportError as exc:
    raise SystemExit(
        "Flask required. Run: pip install flask gunicorn"
    ) from exc


APP_BASE_URL = os.getenv("APP_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("HERMES_WEBHOOK_SECRET", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))

app = Flask(__name__)


def _check_secret(path_secret: Optional[str]) -> bool:
    if not WEBHOOK_SECRET:
        return True
    return path_secret == WEBHOOK_SECRET


def _parse_start(text: Optional[str]) -> tuple[Optional[str], bool]:
    """Return (start_payload, is_start_command)."""
    if not text:
        return None, False
    text = text.strip()
    if not text.startswith("/start"):
        return None, False
    parts = text.split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else None
    return payload or None, True


def _handle_update(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"handled": False, "reason": "no_message"}

    text = message.get("text") or ""
    payload, is_start = _parse_start(text)
    if not is_start:
        return {"handled": False, "reason": "not_start", "text": text[:80]}

    from_user = message.get("from") or {}
    user_id = from_user.get("id")
    if not user_id:
        return {"handled": False, "reason": "no_user_id"}

    username = from_user.get("username")
    result = capture_telegram_start(
        telegram_user_id=int(user_id),
        telegram_username=username,
        start_payload=payload,
        raw_payload=update,
        send_welcome=True,
        notify_admin=True,
    )
    return {"handled": True, "action": "capture_start", "result": result}


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "hermes-telegram-webhook",
        "app_base_url_set": bool(APP_BASE_URL),
        "webhook_secret_set": bool(WEBHOOK_SECRET),
    })


@app.post("/webhook/telegram")
@app.post("/webhook/telegram/<secret>")
def telegram_webhook(secret: Optional[str] = None):
    if not _check_secret(secret):
        return jsonify({"error": "unauthorized"}), 403

    update = request.get_json(silent=True) or {}
    try:
        outcome = _handle_update(update)
        return jsonify({"ok": True, **outcome})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def main() -> None:
    app.run(host="0.0.0.0", port=WEBHOOK_PORT, debug=os.getenv("NODE_ENV") == "development")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
MCM Vendor — Hermes XAUUSD Growth OS v2
Telegram: welcome, admin alerts, country intelligence reports.

Usage:
    python scripts/send_telegram_report.py test-welcome --user-id 123 --username testuser
    python scripts/send_telegram_report.py test-admin --payload "src_xacc_uae_001_uae_goldhook_20260624"
    python scripts/send_telegram_report.py country-report --dry-run
    python scripts/send_telegram_report.py founder-daily --dry-run
    python scripts/send_telegram_report.py founder-daily --weekly --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")


def send_telegram_message(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str = "HTML",
    disable_preview: bool = True,
) -> dict[str, Any]:
    """Send a message via Telegram Bot API. Returns API response dict."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }
    data = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error {exc.code}: {detail}") from exc


def format_welcome_message(*, username: Optional[str], parse_status: str) -> str:
    name = f"@{username}" if username else "there"
    if parse_status == "missing_payload":
        return (
            f"Welcome {name}! 👋\n\n"
            "You're in the Hermes XAUUSD community.\n"
            "Reply anytime if you want gold signals or VIP access."
        )
    return (
        f"Welcome {name}! 👋\n\n"
        "You're in the Hermes XAUUSD community.\n"
        "We'll share daily gold insights and signal updates here.\n"
        "Reply <b>VIP</b> if you want premium access."
    )


def format_admin_join_alert(result: dict[str, Any]) -> str:
    username = result.get("telegram_username") or "—"
    user_id = result.get("telegram_user_id", "—")
    source = result.get("source_account") or "unknown"
    country = result.get("country_target") or "unknown"
    campaign = result.get("campaign_id") or "—"
    status = result.get("parse_status", "—")
    duplicate = "yes" if result.get("is_duplicate") else "no"
    lead_id = result.get("lead_id", "—")

    lines = [
        "🟢 <b>New Telegram Join</b>",
        "",
        f"User: @{username} (<code>{user_id}</code>)",
        f"Source: <code>{source}</code>",
        f"Country: <code>{country}</code>",
        f"Campaign: <code>{campaign}</code>",
        f"Parse: <code>{status}</code>",
        f"Duplicate: {duplicate}",
        f"Lead: <code>{lead_id}</code>",
    ]
    if result.get("telegram_error"):
        lines.extend(["", f"⚠️ Telegram: {result['telegram_error']}"])
    return "\n".join(lines)


def send_welcome_message(
    telegram_user_id: int,
    *,
    username: Optional[str] = None,
    parse_status: str = "ok",
) -> dict[str, Any]:
    text = format_welcome_message(username=username, parse_status=parse_status)
    return send_telegram_message(telegram_user_id, text)


def send_admin_join_alert(result: dict[str, Any]) -> dict[str, Any]:
    if not TELEGRAM_ADMIN_CHAT_ID:
        raise RuntimeError("TELEGRAM_ADMIN_CHAT_ID is not set")
    text = format_admin_join_alert(result)
    return send_telegram_message(TELEGRAM_ADMIN_CHAT_ID, text)


def format_country_opportunity_report(intel: dict[str, Any]) -> str:
    country = intel.get("country_target", "—")
    report_date = intel.get("report_date", "—")
    lines = [
        "📊 <b>Country Opportunity Report</b>",
        f"Date: <code>{report_date}</code> | Country: <b>{country}</b>",
        "",
        f"Posts crawled: <b>{intel.get('posts_crawled', 0)}</b>",
        f"High potential: <b>{intel.get('high_potential_count', 0)}</b>",
        f"Top hashtag: <code>{intel.get('top_hashtag') or '—'}</code>",
        f"Top hook: {intel.get('top_hook') or '—'}",
        f"Top author: @{intel.get('top_author') or '—'}",
        f"Top angle: <code>{intel.get('top_content_angle') or '—'}</code>",
    ]
    if intel.get("noise_warning"):
        lines.extend(["", f"⚠️ {intel['noise_warning']}"])

    rewrite = intel.get("posts_to_rewrite") or []
    if rewrite:
        lines.extend(["", "<b>Posts to rewrite:</b>"])
        for item in rewrite[:3]:
            if isinstance(item, dict):
                lines.append(f"• {item.get('hook', '')[:60]}… <code>{item.get('post_url', '')}</code>")

    seed = intel.get("posts_to_seed") or []
    if seed:
        lines.extend(["", "<b>Comment / seed:</b>"])
        for item in seed[:3]:
            if isinstance(item, dict):
                lines.append(f"• @{item.get('author', '?')} — <code>{item.get('post_url', '')}</code>")

    tasks = intel.get("vendor_task_suggestions") or []
    if tasks:
        lines.extend(["", "<b>Vendor tasks (Tuấn):</b>"])
        for t in tasks[:3]:
            lines.append(f"• {t}")

    return "\n".join(lines)


def send_country_opportunity_report(intel: dict[str, Any]) -> dict[str, Any]:
    if not TELEGRAM_ADMIN_CHAT_ID:
        raise RuntimeError("TELEGRAM_ADMIN_CHAT_ID is not set")
    text = format_country_opportunity_report(intel)
    return send_telegram_message(TELEGRAM_ADMIN_CHAT_ID, text)


def cmd_test_welcome(user_id: int, username: Optional[str]) -> int:
    try:
        resp = send_welcome_message(user_id, username=username, parse_status="ok")
        print(json.dumps({"status": "success", "telegram": resp}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_test_admin(payload: str) -> int:
    # Import here to avoid circular import when sync_to_supabase imports this module
    sys.path.insert(0, os.path.dirname(__file__))
    from sync_to_supabase import get_connection, upsert_telegram_join

    fake_user_id = int(os.getenv("TEST_TELEGRAM_USER_ID", "999000002"))
    fake_username = os.getenv("TEST_TELEGRAM_USERNAME", "phase1_test_user")

    try:
        conn = get_connection()
        result = upsert_telegram_join(
            conn,
            telegram_user_id=fake_user_id,
            telegram_username=fake_username,
            start_payload=payload,
            raw_payload={"test": True, "phase": "phase1"},
        )
        conn.close()
        result["telegram_username"] = fake_username
        result["telegram_user_id"] = fake_user_id

        try:
            admin_resp = send_admin_join_alert(result)
            result["admin_notified"] = True
            result["admin_response"] = admin_resp.get("ok", False)
        except Exception as tg_exc:
            result["admin_notified"] = False
            result["telegram_error"] = str(tg_exc)

        print(json.dumps({"status": "success", "result": result}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_country_report(file_path: Optional[str], dry_run: bool) -> int:
    if file_path:
        with open(file_path, encoding="utf-8") as f:
            intel = json.load(f)
    else:
        sys.path.insert(0, os.path.dirname(__file__))
        from normalize_apify_dataset import process_dataset, sample_posts_canada

        result = process_dataset(sample_posts_canada(), country="Canada", persist=False)
        intel = result.get("country_intelligence", {})

    text = format_country_opportunity_report(intel)
    if dry_run:
        print(text)
        return 0
    try:
        resp = send_country_opportunity_report(intel)
        print(json.dumps({"status": "success", "telegram": resp.get("ok")}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_founder_daily(dry_run: bool, weekly: bool) -> int:
    sys.path.insert(0, os.path.dirname(__file__))
    from health_check import (
        build_health_report,
        build_weekly_review,
        fetch_founder_report_data,
        format_founder_daily_report,
        format_weekly_review,
        get_connection,
    )

    health = build_health_report()
    try:
        conn = get_connection()
        if weekly:
            review = build_weekly_review(conn)
            text = format_weekly_review(review)
        else:
            data = fetch_founder_report_data(conn)
            text = format_founder_daily_report(data, health)
        conn.close()
    except Exception as exc:
        text = format_founder_daily_report(
            {"report_date": date.today().isoformat(), "action_items": [f"Fix DB: {exc}"]},
            health,
        )

    if dry_run:
        print(text)
        return 0

    if not TELEGRAM_ADMIN_CHAT_ID:
        print(json.dumps({"status": "error", "message": "TELEGRAM_ADMIN_CHAT_ID not set"}, indent=2))
        return 1

    try:
        resp = send_telegram_message(TELEGRAM_ADMIN_CHAT_ID, text)
        print(json.dumps({"status": "success", "telegram": resp.get("ok"), "payload_summary": {
            "overall_health": health.get("overall"),
            "failed": health.get("failed_services"),
        }}, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram welcome and admin reports")
    sub = parser.add_subparsers(dest="command", required=True)

    welcome = sub.add_parser("test-welcome", help="Send test welcome message to a user")
    welcome.add_argument("--user-id", type=int, required=True)
    welcome.add_argument("--username", default="testuser")

    admin = sub.add_parser("test-admin", help="Upsert join + send admin alert")
    admin.add_argument(
        "--payload",
        default="src_xacc_uae_001_uae_goldhook_20260624",
    )

    country = sub.add_parser("country-report", help="Send country opportunity report to admin")
    country.add_argument("--file", help="JSON file with country_intelligence object")
    country.add_argument("--dry-run", action="store_true", help="Print only, do not send")

    founder = sub.add_parser("founder-daily", help="Agent 5 — 8PM founder operating report")
    founder.add_argument("--dry-run", action="store_true")
    founder.add_argument("--weekly", action="store_true", help="Send weekly review instead")

    args = parser.parse_args()

    if args.command == "test-welcome":
        return cmd_test_welcome(args.user_id, args.username)
    if args.command == "test-admin":
        return cmd_test_admin(args.payload)
    if args.command == "country-report":
        return cmd_country_report(args.file, args.dry_run)
    if args.command == "founder-daily":
        return cmd_founder_daily(args.dry_run, args.weekly)

    return 1


if __name__ == "__main__":
    sys.exit(main())

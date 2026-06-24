#!/usr/bin/env python3
"""
MCM Vendor — Hermes XAUUSD Growth OS v2
Phase 7: Activepieces webhook test + automation failure logging.

Usage:
    python scripts/activepieces_webhook_test.py health
    python scripts/activepieces_webhook_test.py sample-payload --flow 1
    python scripts/activepieces_webhook_test.py send --flow 1 --dry-run
    python scripts/activepieces_webhook_test.py send --flow 1
    python scripts/activepieces_webhook_test.py log-failure --flow 3 --message "test failure"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
FLOWS_CONFIG = ROOT / "config" / "activepieces-flows.json"

DATABASE_URL = os.getenv("DATABASE_URL", "")
ACTIVEPIECES_WEBHOOK_SECRET = os.getenv("ACTIVEPIECES_WEBHOOK_SECRET", "")

FLOW_WEBHOOK_ENV = {
    1: "ACTIVEPIECES_WEBHOOK_FLOW1",
    2: "ACTIVEPIECES_WEBHOOK_FLOW2",
    3: "ACTIVEPIECES_WEBHOOK_FLOW3",
    4: "ACTIVEPIECES_WEBHOOK_FLOW4",
    5: "ACTIVEPIECES_WEBHOOK_FLOW5",
    6: "ACTIVEPIECES_WEBHOOK_FLOW6",
}


def load_flows_config() -> dict[str, Any]:
    with open(FLOWS_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL)


def log_automation(
    conn,
    *,
    flow: int,
    status: str = "success",
    message: Optional[str] = None,
    error_detail: Optional[str] = None,
    entity_type: str = "automation",
    entity_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO activity_logs (
                entity_type, entity_id, action, status, message,
                actor, source, error_detail, payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                entity_type,
                entity_id,
                f"activepieces_flow_{flow}",
                status,
                message,
                "activepieces",
                "automation",
                error_detail,
                json.dumps(payload or {}),
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return str(row[0])


def sample_payload(flow: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    uid = lambda: str(uuid.uuid4())

    samples: dict[int, dict[str, Any]] = {
        1: {
            "type": "INSERT",
            "table": "telegram_joins",
            "flow_id": "flow_01",
            "record": {
                "id": uid(),
                "lead_id": uid(),
                "telegram_user_id": 123456789,
                "telegram_username": "phase7_test_user",
                "start_payload": "src_xacc_uae_001_uae_goldhook_20260624_hook001",
                "source_account": "xacc_uae_001",
                "country_target": "uae",
                "campaign_id": "goldhook_20260624",
                "content_id": "hook001",
                "parse_status": "ok",
                "is_duplicate": False,
                "join_time": now,
            },
        },
        2: {
            "type": "INSERT",
            "table": "crm_stage_events",
            "flow_id": "flow_02",
            "record": {
                "id": uid(),
                "lead_id": uid(),
                "from_stage": "Telegram Joined",
                "to_stage": "Warm Member",
                "reason": "stage_change",
                "triggered_by": "activepieces_test",
                "twenty_synced": False,
            },
        },
        3: {
            "type": "INSERT",
            "table": "apify_posts",
            "flow_id": "flow_03",
            "record": {
                "id": uid(),
                "country_target": "Canada",
                "hashtag": "#xauusd",
                "post_url": "https://x.com/trader/status/phase7test",
                "hook_extracted": "Gold breakout above 2350",
                "content_angle": "breakout",
                "lead_potential": "High",
                "engagement_score": 150,
            },
        },
        4: {
            "type": "INSERT",
            "table": "daily_kpis",
            "flow_id": "flow_04",
            "record": {
                "kpi_date": datetime.now(timezone.utc).date().isoformat(),
                "telegram_joins": 42,
                "top_country": "uae",
                "top_x_account": "xacc_uae_001",
                "paid_vip": 3,
                "renewal_risk": 5,
                "apify_posts_crawled": 120,
                "vendor_tasks_overdue": 2,
            },
        },
        5: {
            "flow": "vendor_task_overdue",
            "flow_id": "flow_05",
            "tasks": [
                {
                    "id": uid(),
                    "title": "[UAE] #xauusd breakout",
                    "country_target": "uae",
                    "deadline": now,
                    "status": "assigned",
                    "plane_task_id": "plane-test-id",
                }
            ],
        },
        6: {
            "flow": "renewal_risk",
            "flow_id": "flow_06",
            "members": [
                {
                    "lead_id": uid(),
                    "telegram_user_id": 987654321,
                    "telegram_username": "inactive_member",
                    "days_inactive": 5,
                }
            ],
        },
    }
    if flow not in samples:
        raise ValueError(f"Unknown flow {flow}. Use 1-6.")
    return samples[flow]


def get_webhook_url(flow: int) -> str:
    env_name = FLOW_WEBHOOK_ENV.get(flow)
    if not env_name:
        raise ValueError(f"No webhook env for flow {flow}")
    url = os.getenv(env_name, "")
    if not url:
        raise RuntimeError(f"{env_name} is not set in .env")
    return url


def send_webhook(flow: int, payload: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {
            "dry_run": True,
            "flow": flow,
            "url_env": FLOW_WEBHOOK_ENV[flow],
            "payload": payload,
        }

    url = get_webhook_url(flow)
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if ACTIVEPIECES_WEBHOOK_SECRET:
        headers["Authorization"] = f"Bearer {ACTIVEPIECES_WEBHOOK_SECRET}"

    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return {
                "status": "sent",
                "http_code": resp.status,
                "response": json.loads(body) if body else {},
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Webhook HTTP {exc.code}: {detail}") from exc


def cmd_health() -> int:
    config = load_flows_config()
    webhooks = {
        f"flow_{i}": bool(os.getenv(env))
        for i, env in FLOW_WEBHOOK_ENV.items()
    }
    print(json.dumps({
        "status": "ok",
        "flows_defined": len(config.get("flows", [])),
        "database_url_set": bool(DATABASE_URL),
        "webhook_secret_set": bool(ACTIVEPIECES_WEBHOOK_SECRET),
        "webhooks_configured": webhooks,
    }, indent=2))
    return 0


def cmd_sample(flow: int) -> int:
    print(json.dumps(sample_payload(flow), indent=2))
    return 0


def cmd_send(flow: int, dry_run: bool) -> int:
    payload = sample_payload(flow)
    try:
        result = send_webhook(flow, payload, dry_run=dry_run)
        if not dry_run and DATABASE_URL:
            try:
                conn = get_connection()
                log_automation(
                    conn,
                    flow=flow,
                    status="success",
                    message=f"Webhook test sent for flow {flow}",
                    entity_id=payload.get("record", {}).get("id") if "record" in payload else None,
                    payload={"webhook_result": result},
                )
                conn.close()
            except Exception:
                pass
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        if DATABASE_URL:
            try:
                conn = get_connection()
                log_automation(
                    conn,
                    flow=flow,
                    status="failure",
                    message=f"Webhook test failed flow {flow}",
                    error_detail=str(exc),
                    payload=payload,
                )
                conn.close()
            except Exception:
                pass
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_log_failure(flow: int, message: str, error: Optional[str], entity_id: Optional[str]) -> int:
    try:
        conn = get_connection()
        log_id = log_automation(
            conn,
            flow=flow,
            status="failure",
            message=message,
            error_detail=error,
            entity_id=entity_id,
            payload={"test": True, "phase": "phase7"},
        )
        conn.close()
        print(json.dumps({"status": "success", "activity_log_id": log_id}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_test() -> int:
    """Phase 7 acceptance: sample all flows + log failure test."""
    results = {"samples": {}, "log_failure": None}
    for i in range(1, 7):
        results["samples"][f"flow_{i}"] = sample_payload(i).get("flow_id")
    try:
        conn = get_connection()
        results["log_failure"] = log_automation(
            conn,
            flow=99,
            status="failure",
            message="Phase 7 acceptance failure path test",
            error_detail="intentional test",
            payload={"acceptance": True},
        )
        conn.close()
    except Exception as exc:
        results["log_failure_error"] = str(exc)
    print(json.dumps(results, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Activepieces webhook test utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("test", help="Phase 7 acceptance — samples + log failure")

    sample = sub.add_parser("sample-payload", help="Print sample webhook JSON")
    sample.add_argument("--flow", type=int, required=True, choices=range(1, 7))

    send = sub.add_parser("send", help="POST sample payload to Activepieces webhook")
    send.add_argument("--flow", type=int, required=True, choices=range(1, 7))
    send.add_argument("--dry-run", action="store_true")

    fail = sub.add_parser("log-failure", help="Write activity_logs failure row")
    fail.add_argument("--flow", type=int, required=True)
    fail.add_argument("--message", default="Activepieces flow failed")
    fail.add_argument("--error")
    fail.add_argument("--entity-id")

    args = parser.parse_args()

    if args.command == "health":
        return cmd_health()
    if args.command == "test":
        return cmd_test()
    if args.command == "sample-payload":
        return cmd_sample(args.flow)
    if args.command == "send":
        return cmd_send(args.flow, args.dry_run)
    if args.command == "log-failure":
        return cmd_log_failure(args.flow, args.message, args.error, args.entity_id)

    return 1


if __name__ == "__main__":
    sys.exit(main())

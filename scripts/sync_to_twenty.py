#!/usr/bin/env python3
"""
MCM Vendor — Hermes XAUUSD Growth OS v2
Phase 2: Sync Supabase leads → Twenty CRM (Person + Opportunity).

Supabase remains source of truth. Twenty is pipeline visibility only.

Usage:
    python scripts/sync_to_twenty.py health
    python scripts/sync_to_twenty.py sync-lead --lead-id <uuid>
    python scripts/sync_to_twenty.py sync-lead --telegram-user-id 999000001
    python scripts/sync_to_twenty.py test-sync --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_CONFIG = ROOT / "config" / "twenty-pipeline.json"

DATABASE_URL = os.getenv("DATABASE_URL", "")
TWENTY_API_URL = os.getenv("TWENTY_API_URL", "").rstrip("/")
TWENTY_API_KEY = os.getenv("TWENTY_API_KEY", "")
RENEWAL_RISK_DAYS = int(os.getenv("TWENTY_RENEWAL_RISK_DAYS", "3"))


def load_pipeline_config() -> dict[str, Any]:
    with open(PIPELINE_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary python-dotenv")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL)


def log_activity(
    conn,
    *,
    entity_type: str,
    entity_id: Optional[str],
    action: str,
    status: str = "success",
    message: Optional[str] = None,
    actor: str = "sync_to_twenty",
    source: str = "twenty",
    error_detail: Optional[str] = None,
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
                entity_type, entity_id, action, status, message,
                actor, source, error_detail, json.dumps(payload or {}),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return str(row[0])


def twenty_request(
    method: str,
    path: str,
    body: Optional[dict[str, Any]] = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "method": method, "path": path, "body": body}

    if not TWENTY_API_URL or not TWENTY_API_KEY:
        raise RuntimeError("TWENTY_API_URL and TWENTY_API_KEY must be set")

    url = f"{TWENTY_API_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TWENTY_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Twenty API {exc.code} {method} {path}: {detail}") from exc


def map_stage(hermes_stage: str, config: dict[str, Any]) -> str:
    stage_map = config.get("twenty_stage_map", {})
    return stage_map.get(hermes_stage, hermes_stage.replace(" ", "_").replace("/", "_").upper())


def fetch_lead(conn, *, lead_id: Optional[str] = None, telegram_user_id: Optional[int] = None) -> dict[str, Any]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if lead_id:
            cur.execute("SELECT * FROM leads WHERE id = %s", (lead_id,))
        elif telegram_user_id is not None:
            cur.execute("SELECT * FROM leads WHERE telegram_user_id = %s", (telegram_user_id,))
        else:
            raise ValueError("lead_id or telegram_user_id required")
        row = cur.fetchone()
        if not row:
            raise ValueError("Lead not found")
        return dict(row)


def build_person_payload(lead: dict[str, Any]) -> dict[str, Any]:
    username = lead.get("telegram_username") or f"user_{lead['telegram_user_id']}"
    return {
        "name": {
            "firstName": username,
            "lastName": f"TG-{lead['telegram_user_id']}",
        },
        "telegramUserId": str(lead["telegram_user_id"]),
        "city": lead.get("country_target") or "unknown",
        "jobTitle": lead.get("current_stage"),
        "xLink": {
            "primaryLinkLabel": lead.get("source_account") or "",
            "primaryLinkUrl": "",
        },
    }


def build_opportunity_payload(lead: dict[str, Any], config: dict[str, Any], person_id: str) -> dict[str, Any]:
    stage = map_stage(lead["current_stage"], config)
    name_parts = [
        lead.get("telegram_username") or str(lead["telegram_user_id"]),
        lead.get("country_target") or "unknown",
        lead.get("campaign_id") or "no-campaign",
    ]
    return {
        "name": " | ".join(name_parts),
        "stage": stage,
        "amount": {
            "amountMicros": 0,
            "currencyCode": "USD",
        },
        "pointOfContactId": person_id,
        "hermesLeadId": str(lead["id"]),
        "sourceAccount": lead.get("source_account"),
        "countryTarget": lead.get("country_target"),
        "campaignId": lead.get("campaign_id"),
    }


def save_twenty_ids(conn, lead_id: str, person_id: str, opportunity_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE leads SET
                raw_payload = raw_payload || %s::jsonb,
                updated_at = %s
            WHERE id = %s
            """,
            (
                json.dumps({
                    "twenty_person_id": person_id,
                    "twenty_opportunity_id": opportunity_id,
                    "twenty_synced_at": datetime.now(timezone.utc).isoformat(),
                }),
                datetime.now(timezone.utc),
                lead_id,
            ),
        )
    conn.commit()


def log_stage_event(
    conn,
    lead_id: str,
    from_stage: Optional[str],
    to_stage: str,
    *,
    twenty_synced: bool,
    twenty_sync_error: Optional[str] = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO crm_stage_events (
                lead_id, from_stage, to_stage, reason, triggered_by,
                twenty_synced, twenty_sync_error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (lead_id, from_stage, to_stage, "twenty_sync", "agent4", twenty_synced, twenty_sync_error),
        )
    conn.commit()


def sync_lead_to_twenty(
    conn,
    lead: dict[str, Any],
    *,
    dry_run: bool = False,
    config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    config = config or load_pipeline_config()
    raw = lead.get("raw_payload") or {}
    if isinstance(raw, str):
        raw = json.loads(raw)

    person_id = raw.get("twenty_person_id")
    opportunity_id = raw.get("twenty_opportunity_id")
    previous_stage = raw.get("twenty_last_stage")

    result: dict[str, Any] = {
        "lead_id": str(lead["id"]),
        "hermes_stage": lead["current_stage"],
        "twenty_stage": map_stage(lead["current_stage"], config),
        "created_person": False,
        "created_opportunity": False,
        "updated_opportunity": False,
    }

    try:
        if not person_id:
            person_body = build_person_payload(lead)
            person_resp = twenty_request("POST", "/rest/people", person_body, dry_run=dry_run)
            person_id = (
                person_resp.get("data", {}).get("createPerson", {}).get("id")
                or person_resp.get("data", {}).get("id")
                or (f"dry-person-{lead['id']}" if dry_run else None)
            )
            if not person_id:
                raise RuntimeError(f"Could not parse person id from Twenty response: {person_resp}")
            result["created_person"] = True
            result["twenty_person_id"] = person_id

        if not opportunity_id:
            opp_body = build_opportunity_payload(lead, config, person_id)
            opp_resp = twenty_request("POST", "/rest/opportunities", opp_body, dry_run=dry_run)
            opportunity_id = (
                opp_resp.get("data", {}).get("createOpportunity", {}).get("id")
                or opp_resp.get("data", {}).get("id")
                or (f"dry-opp-{lead['id']}" if dry_run else None)
            )
            if not opportunity_id:
                raise RuntimeError(f"Could not parse opportunity id from Twenty response: {opp_resp}")
            result["created_opportunity"] = True
            result["twenty_opportunity_id"] = opportunity_id
        elif previous_stage != lead["current_stage"]:
            patch_body = {"stage": map_stage(lead["current_stage"], config)}
            twenty_request("PATCH", f"/rest/opportunities/{opportunity_id}", patch_body, dry_run=dry_run)
            result["updated_opportunity"] = True
            result["twenty_opportunity_id"] = opportunity_id

        if not dry_run:
            save_twenty_ids(conn, str(lead["id"]), person_id, opportunity_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE leads SET raw_payload = raw_payload || %s::jsonb WHERE id = %s
                    """,
                    (json.dumps({"twenty_last_stage": lead["current_stage"]}), str(lead["id"])),
                )
            conn.commit()

        log_stage_event(
            conn,
            str(lead["id"]),
            previous_stage,
            lead["current_stage"],
            twenty_synced=True,
        )
        log_activity(
            conn,
            entity_type="leads",
            entity_id=str(lead["id"]),
            action="twenty_sync",
            status="success",
            message="Lead synced to Twenty CRM",
            payload=result,
        )
        result["status"] = "success"
        return result

    except Exception as exc:
        log_stage_event(
            conn,
            str(lead["id"]),
            previous_stage,
            lead["current_stage"],
            twenty_synced=False,
            twenty_sync_error=str(exc),
        )
        log_activity(
            conn,
            entity_type="leads",
            entity_id=str(lead["id"]),
            action="twenty_sync",
            status="failure",
            message="Twenty CRM sync failed",
            error_detail=str(exc),
            payload={"lead_id": str(lead["id"]), "stage": lead["current_stage"]},
        )
        raise


def apply_stage_rules(conn, lead: dict[str, Any]) -> dict[str, Any]:
    """Derive target stage from Supabase lead/member signals before Twenty sync."""
    new_stage = lead["current_stage"]
    if lead.get("paid_flag"):
        new_stage = "Paid / VIP"
    elif lead.get("inactive_days", 0) > RENEWAL_RISK_DAYS:
        new_stage = "Renewal Risk"

    if new_stage != lead["current_stage"]:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE leads SET current_stage = %s, stage_updated_at = %s WHERE id = %s
                RETURNING *
                """,
                (new_stage, datetime.now(timezone.utc), lead["id"]),
            )
            updated = cur.fetchone()
        conn.commit()
        if updated:
            return dict(updated)
    return lead


def cmd_health() -> int:
    config = load_pipeline_config()
    out = {
        "status": "ok",
        "database_url_set": bool(DATABASE_URL),
        "twenty_api_url_set": bool(TWENTY_API_URL),
        "twenty_api_key_set": bool(TWENTY_API_KEY),
        "pipeline": config.get("pipeline"),
        "stages": len(config.get("stages", [])),
    }
    if TWENTY_API_URL and TWENTY_API_KEY:
        try:
            twenty_request("GET", "/rest/people?limit=1")
            out["twenty_api"] = "reachable"
        except Exception as exc:
            out["twenty_api"] = f"error: {exc}"
    print(json.dumps(out, indent=2))
    return 0


def cmd_sync_lead(lead_id: Optional[str], telegram_user_id: Optional[int], dry_run: bool) -> int:
    try:
        conn = get_connection()
        lead = fetch_lead(conn, lead_id=lead_id, telegram_user_id=telegram_user_id)
        lead = apply_stage_rules(conn, lead)
        result = sync_lead_to_twenty(conn, lead, dry_run=dry_run)
        conn.close()
        print(json.dumps({"status": "success", "result": result}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_test_sync(dry_run: bool) -> int:
    """Sync test lead (TEST_TELEGRAM_USER_ID) — dry-run by default."""
    user_id = int(os.getenv("TEST_TELEGRAM_USER_ID", "999000001"))
    return cmd_sync_lead(None, user_id, dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Supabase leads to Twenty CRM")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Check config and Twenty API connectivity")

    sync = sub.add_parser("sync-lead", help="Sync one lead to Twenty")
    sync.add_argument("--lead-id")
    sync.add_argument("--telegram-user-id", type=int)
    sync.add_argument("--dry-run", action="store_true")

    test = sub.add_parser("test-sync", help="Sync TEST_TELEGRAM_USER_ID lead")
    test.add_argument("--dry-run", action="store_true", default=True)
    test.add_argument("--live", action="store_true", help="Actually call Twenty API")

    args = parser.parse_args()

    if args.command == "health":
        return cmd_health()
    if args.command == "sync-lead":
        if not args.lead_id and not args.telegram_user_id:
            print(json.dumps({"status": "error", "message": "Provide --lead-id or --telegram-user-id"}))
            return 1
        return cmd_sync_lead(args.lead_id, args.telegram_user_id, args.dry_run)
    if args.command == "test-sync":
        return cmd_test_sync(dry_run=not args.live)

    return 1


if __name__ == "__main__":
    sys.exit(main())

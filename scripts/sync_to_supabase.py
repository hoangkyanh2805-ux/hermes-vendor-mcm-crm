#!/usr/bin/env python3
"""
MCM Vendor — Hermes XAUUSD Growth OS v2
Phase 0–1: Supabase sync + Telegram /start capture.

Writes leads, telegram joins, and activity logs to Supabase/Postgres.
No Google Sheet dependency.

Usage:
    python scripts/sync_to_supabase.py health
    python scripts/sync_to_supabase.py test-join
    python scripts/sync_to_supabase.py test-join --payload "src_xacc_uae_001_uae_goldhook_20260624"
    python scripts/sync_to_supabase.py capture-start --user-id 123456 --username alice --payload "src_..."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
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

DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
CONTENT_WINNING_JOIN_RATE = float(os.getenv("CONTENT_WINNING_JOIN_RATE", "0.05"))

CONTENT_STATUSES = frozenset({
    "draft", "assigned", "posted", "tracked", "winning", "failed", "archived",
})

# Deep link: src_{x_account_id}_{country}_{campaign_id}[_{content_id}]
# Example: src_xacc_uae_001_uae_goldhook_20260624
KNOWN_COUNTRY_TOKENS = {
    "uae", "uk", "canada", "italy", "germany", "france", "poland",
    "ksa", "saudi", "saudiarabia", "unitedarabemirates",
}


@dataclass
class ParsedStartPayload:
    source_account: Optional[str]
    country_target: Optional[str]
    campaign_id: Optional[str]
    content_id: Optional[str]
    parse_status: str
    raw_payload: str


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary python-dotenv")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set in environment")
    return psycopg2.connect(DATABASE_URL)


def log_activity(
    conn,
    *,
    entity_type: str,
    entity_id: Optional[str],
    action: str,
    status: str = "success",
    message: Optional[str] = None,
    actor: str = "sync_to_supabase",
    source: str = "script",
    error_detail: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> str:
    """Insert into activity_logs. Returns log id."""
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
                action,
                status,
                message,
                actor,
                source,
                error_detail,
                json.dumps(payload or {}),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return str(row[0])


def parse_start_payload(payload: Optional[str]) -> ParsedStartPayload:
    if not payload or not payload.strip():
        return ParsedStartPayload(
            source_account=None,
            country_target=None,
            campaign_id=None,
            content_id=None,
            parse_status="missing_payload",
            raw_payload=payload or "",
        )

    text = payload.strip()
    if text.startswith("src_"):
        text = text[4:]

    # Rightmost known country token splits x_account_id from campaign_id
    parts = text.split("_")
    for i in range(len(parts) - 2, 0, -1):
        if parts[i].lower() not in KNOWN_COUNTRY_TOKENS:
            continue
        campaign_parts = parts[i + 1 :]
        if not campaign_parts:
            continue
        if len(campaign_parts) >= 2:
            campaign_id = "_".join(campaign_parts[:-1])
            content_id = campaign_parts[-1]
        else:
            campaign_id = "_".join(campaign_parts)
            content_id = None
        return ParsedStartPayload(
            source_account="_".join(parts[:i]),
            country_target=parts[i],
            campaign_id=campaign_id,
            content_id=content_id,
            parse_status="ok",
            raw_payload=payload,
        )

    # Simple three-part fallback: account_country_campaign
    if len(parts) == 3:
        return ParsedStartPayload(
            source_account=parts[0],
            country_target=parts[1],
            campaign_id=parts[2],
            content_id=None,
            parse_status="ok",
            raw_payload=payload,
        )

    return ParsedStartPayload(
        source_account=None,
        country_target=None,
        campaign_id=None,
        content_id=None,
        parse_status="invalid",
        raw_payload=payload,
    )


def validate_references(conn, parsed: ParsedStartPayload) -> str:
    """Return parse_status after validating FK references and country."""
    if parsed.parse_status != "ok":
        return parsed.parse_status

    if parsed.country_target and parsed.country_target.lower() not in KNOWN_COUNTRY_TOKENS:
        return "unknown_country"

    with conn.cursor() as cur:
        if parsed.source_account:
            cur.execute("SELECT 1 FROM x_accounts WHERE id = %s", (parsed.source_account,))
            if not cur.fetchone():
                return "unknown_source"

        if parsed.campaign_id:
            cur.execute("SELECT 1 FROM campaigns WHERE id = %s", (parsed.campaign_id,))
            if not cur.fetchone():
                if parsed.content_id:
                    combined = f"{parsed.campaign_id}_{parsed.content_id}"
                    cur.execute("SELECT 1 FROM campaigns WHERE id = %s", (combined,))
                    if cur.fetchone():
                        return "ok"
                return "invalid"

        if parsed.content_id:
            cur.execute("SELECT 1 FROM content_assets WHERE id = %s", (parsed.content_id,))
            if not cur.fetchone():
                return "invalid"

    return "ok"


def ensure_content_asset(
    conn,
    content_id: str,
    *,
    hook: Optional[str] = None,
    angle: Optional[str] = None,
    hashtag: Optional[str] = None,
    country_target: Optional[str] = None,
    x_account_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    vendor_id: Optional[str] = None,
    source_post_url: Optional[str] = None,
    status: str = "draft",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO content_assets (
                id, hook, angle, hashtag, country_target, x_account_id,
                campaign_id, vendor_id, source_post_url, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                hook = COALESCE(EXCLUDED.hook, content_assets.hook),
                angle = COALESCE(EXCLUDED.angle, content_assets.angle),
                hashtag = COALESCE(EXCLUDED.hashtag, content_assets.hashtag),
                country_target = COALESCE(EXCLUDED.country_target, content_assets.country_target),
                x_account_id = COALESCE(EXCLUDED.x_account_id, content_assets.x_account_id),
                campaign_id = COALESCE(EXCLUDED.campaign_id, content_assets.campaign_id),
                vendor_id = COALESCE(EXCLUDED.vendor_id, content_assets.vendor_id),
                source_post_url = COALESCE(EXCLUDED.source_post_url, content_assets.source_post_url),
                status = CASE
                    WHEN content_assets.status = 'winning' THEN content_assets.status
                    ELSE COALESCE(EXCLUDED.status, content_assets.status)
                END,
                updated_at = NOW()
            """,
            (
                content_id, hook, angle, hashtag, country_target,
                x_account_id, campaign_id, vendor_id, source_post_url, status,
            ),
        )
    conn.commit()


def insert_content_performance(
    conn,
    *,
    content_id: str,
    post_url: Optional[str] = None,
    source_post_url: Optional[str] = None,
    x_account_id: Optional[str] = None,
    vendor_id: Optional[str] = None,
    country_target: Optional[str] = None,
    campaign_id: Optional[str] = None,
    hook: Optional[str] = None,
    angle: Optional[str] = None,
    hashtag: Optional[str] = None,
    posted_at: Optional[datetime] = None,
    views: int = 0,
    likes: int = 0,
    replies: int = 0,
    reposts: int = 0,
    clicks: int = 0,
    telegram_joins: int = 0,
    status: str = "posted",
    notes: Optional[str] = None,
    raw_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if status not in CONTENT_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    ensure_content_asset(
        conn,
        content_id,
        hook=hook,
        angle=angle,
        hashtag=hashtag,
        country_target=country_target,
        x_account_id=x_account_id,
        campaign_id=campaign_id,
        vendor_id=vendor_id,
        source_post_url=source_post_url,
        status=status if status != "tracked" else "posted",
    )

    now = posted_at or datetime.now(timezone.utc)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO content_performance (
                content_id, source_post_url, x_account_id, vendor_id, country_target,
                campaign_id, hook, angle, hashtag, post_url, posted_at,
                views, likes, replies, reposts, clicks, telegram_joins, status, notes, raw_payload
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (content_id) DO UPDATE SET
                post_url = COALESCE(EXCLUDED.post_url, content_performance.post_url),
                posted_at = COALESCE(EXCLUDED.posted_at, content_performance.posted_at),
                views = EXCLUDED.views,
                likes = EXCLUDED.likes,
                replies = EXCLUDED.replies,
                reposts = EXCLUDED.reposts,
                clicks = EXCLUDED.clicks,
                telegram_joins = EXCLUDED.telegram_joins,
                status = EXCLUDED.status,
                notes = COALESCE(EXCLUDED.notes, content_performance.notes),
                raw_payload = content_performance.raw_payload || EXCLUDED.raw_payload,
                updated_at = NOW()
            RETURNING id, content_id, clicks, telegram_joins, join_rate, status
            """,
            (
                content_id, source_post_url, x_account_id, vendor_id, country_target,
                campaign_id, hook, angle, hashtag, post_url, now,
                views, likes, replies, reposts, clicks, telegram_joins, status, notes,
                json.dumps(raw_payload or {}),
            ),
        )
        row = dict(cur.fetchone())
    conn.commit()

    log_activity(
        conn,
        entity_type="content_performance",
        entity_id=str(row["id"]),
        action="insert",
        message=f"Content performance recorded: {content_id}",
        payload={"content_id": content_id, "status": status},
    )
    return row


def update_content_metrics(
    conn,
    content_id: str,
    *,
    views: Optional[int] = None,
    likes: Optional[int] = None,
    replies: Optional[int] = None,
    reposts: Optional[int] = None,
    clicks: Optional[int] = None,
    telegram_joins: Optional[int] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    sets: list[str] = ["updated_at = NOW()"]
    params: list[Any] = []

    field_map = {
        "views": views,
        "likes": likes,
        "replies": replies,
        "reposts": reposts,
        "clicks": clicks,
        "telegram_joins": telegram_joins,
        "status": status,
        "notes": notes,
    }
    for col, val in field_map.items():
        if val is not None:
            if col == "status" and val not in CONTENT_STATUSES:
                raise ValueError(f"Invalid status: {val}")
            sets.append(f"{col} = %s")
            params.append(val)

    if status == "posted":
        sets.append("posted_at = COALESCE(posted_at, NOW())")
    if len(sets) == 1:
        raise ValueError("No metrics provided to update")

    params.append(content_id)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            UPDATE content_performance SET {", ".join(sets)}
            WHERE content_id = %s
            RETURNING id, content_id, views, likes, clicks, telegram_joins, join_rate, status
            """,
            params,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"content_performance not found for content_id={content_id}")
        result = dict(row)
    conn.commit()

    suggest_winning = (
        result.get("join_rate") is not None
        and float(result["join_rate"]) >= CONTENT_WINNING_JOIN_RATE
        and result.get("status") not in ("winning", "archived", "failed")
    )
    if suggest_winning:
        result["suggest_mark_winning"] = True

    log_activity(
        conn,
        entity_type="content_performance",
        entity_id=str(result["id"]),
        action="update_metrics",
        message="Content metrics updated",
        payload={"content_id": content_id, "join_rate": str(result.get("join_rate"))},
    )
    return result


def mark_content_winning(conn, content_id: str, *, notes: Optional[str] = None) -> dict[str, Any]:
    return update_content_metrics(conn, content_id, status="winning", notes=notes)


def attribute_content_join(conn, content_id: str) -> Optional[dict[str, Any]]:
    """Increment telegram_joins when a /start payload includes content_id."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            UPDATE content_performance SET
                telegram_joins = telegram_joins + 1,
                status = CASE
                    WHEN status IN ('posted', 'assigned', 'draft') THEN 'tracked'
                    ELSE status
                END,
                updated_at = NOW()
            WHERE content_id = %s
            RETURNING id, content_id, telegram_joins, clicks, join_rate, status
            """,
            (content_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    conn.commit()
    result = dict(row)
    log_activity(
        conn,
        entity_type="content_performance",
        entity_id=str(result["id"]),
        action="attribute_join",
        message=f"Telegram join attributed to content {content_id}",
        payload=result,
    )
    return result


def upsert_telegram_join(
    conn,
    *,
    telegram_user_id: int,
    telegram_username: Optional[str],
    start_payload: Optional[str],
    raw_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Create or update telegram_joins and leads.
    Returns result dict with ids and status.
    """
    parsed = parse_start_payload(start_payload)
    parse_status = validate_references(conn, parsed)

    if parse_status == "missing_payload":
        parsed = ParsedStartPayload(
            source_account=None,
            country_target="unknown",
            campaign_id=None,
            content_id=None,
            parse_status="missing_payload",
            raw_payload=parsed.raw_payload,
        )
    elif parse_status == "unknown_source":
        parsed = ParsedStartPayload(
            source_account=parsed.source_account,
            country_target=parsed.country_target or "unknown",
            campaign_id=parsed.campaign_id,
            content_id=parsed.content_id,
            parse_status="unknown_source",
            raw_payload=parsed.raw_payload,
        )
    elif parse_status == "unknown_country":
        parsed = ParsedStartPayload(
            source_account=parsed.source_account,
            country_target=parsed.country_target,
            campaign_id=parsed.campaign_id,
            content_id=parsed.content_id,
            parse_status="unknown_country",
            raw_payload=parsed.raw_payload,
        )
    elif parse_status == "invalid":
        parsed = ParsedStartPayload(
            source_account=parsed.source_account,
            country_target=parsed.country_target,
            campaign_id=None,
            content_id=parsed.content_id,
            parse_status="invalid",
            raw_payload=parsed.raw_payload,
        )

    now = datetime.now(timezone.utc)
    is_duplicate = False
    lead_id: Optional[str] = None
    join_id: Optional[str] = None

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, lead_id FROM telegram_joins WHERE telegram_user_id = %s ORDER BY created_at DESC LIMIT 1",
            (telegram_user_id,),
        )
        existing_join = cur.fetchone()

        cur.execute(
            "SELECT id, current_stage FROM leads WHERE telegram_user_id = %s",
            (telegram_user_id,),
        )
        existing_lead = cur.fetchone()

        if existing_lead:
            is_duplicate = True
            lead_id = str(existing_lead["id"])
            stage = "Telegram Joined" if parse_status in (
                "ok", "missing_payload", "unknown_source", "unknown_country"
            ) else existing_lead["current_stage"]
            cur.execute(
                """
                UPDATE leads SET
                    telegram_username = COALESCE(%s, telegram_username),
                    source_account = COALESCE(%s, source_account),
                    country_target = COALESCE(%s, country_target),
                    campaign_id = COALESCE(%s, campaign_id),
                    content_id = COALESCE(%s, content_id),
                    join_time = COALESCE(join_time, %s),
                    current_stage = %s,
                    stage_updated_at = CASE WHEN current_stage IS DISTINCT FROM %s THEN %s ELSE stage_updated_at END,
                    raw_payload = raw_payload || %s::jsonb,
                    updated_at = %s
                WHERE id = %s
                RETURNING id
                """,
                (
                    telegram_username,
                    parsed.source_account,
                    parsed.country_target,
                    parsed.campaign_id,
                    parsed.content_id,
                    now,
                    stage,
                    stage,
                    now,
                    json.dumps(raw_payload or {}),
                    now,
                    lead_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO leads (
                    source_account, source_platform, country_target, campaign_id,
                    telegram_user_id, telegram_username, join_time,
                    current_stage, stage_updated_at, content_id, raw_payload
                ) VALUES (%s, 'telegram', %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    parsed.source_account,
                    parsed.country_target,
                    parsed.campaign_id,
                    telegram_user_id,
                    telegram_username,
                    now,
                    "Telegram Joined" if parse_status != "missing_payload" else "New X Visitor",
                    now,
                    parsed.content_id,
                    json.dumps({
                        "start_payload": start_payload,
                        "parse_status": parse_status,
                        **(raw_payload or {}),
                    }),
                ),
            )
            lead_id = str(cur.fetchone()["id"])

        if existing_join:
            cur.execute(
                """
                UPDATE telegram_joins SET
                    lead_id = %s,
                    telegram_username = COALESCE(%s, telegram_username),
                    start_payload = %s,
                    source_account = %s,
                    country_target = %s,
                    campaign_id = %s,
                    content_id = %s,
                    is_duplicate = TRUE,
                    parse_status = %s,
                    raw_payload = raw_payload || %s::jsonb,
                    updated_at = %s
                WHERE id = %s
                RETURNING id
                """,
                (
                    lead_id,
                    telegram_username,
                    start_payload,
                    parsed.source_account,
                    parsed.country_target,
                    parsed.campaign_id,
                    parsed.content_id,
                    parse_status,
                    json.dumps(raw_payload or {}),
                    now,
                    existing_join["id"],
                ),
            )
            join_id = str(cur.fetchone()["id"])
        else:
            cur.execute(
                """
                INSERT INTO telegram_joins (
                    lead_id, telegram_user_id, telegram_username, start_payload,
                    source_account, country_target, campaign_id, content_id,
                    join_time, is_duplicate, parse_status, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    lead_id,
                    telegram_user_id,
                    telegram_username,
                    start_payload,
                    parsed.source_account,
                    parsed.country_target,
                    parsed.campaign_id,
                    parsed.content_id,
                    now,
                    is_duplicate,
                    parse_status,
                    json.dumps({
                        "start_payload": start_payload,
                        **(raw_payload or {}),
                    }),
                ),
            )
            join_id = str(cur.fetchone()["id"])

    conn.commit()

    content_attribution = None
    if parsed.content_id and not is_duplicate:
        try:
            content_attribution = attribute_content_join(conn, parsed.content_id)
        except Exception as exc:
            log_activity(
                conn,
                entity_type="content_performance",
                entity_id=parsed.content_id,
                action="attribute_join",
                status="failure",
                message="Failed to attribute join to content",
                error_detail=str(exc),
                payload={"content_id": parsed.content_id, "lead_id": lead_id},
            )

    log_activity(
        conn,
        entity_type="telegram_joins",
        entity_id=join_id,
        action="upsert",
        status="success",
        message="Telegram join synced to Supabase",
        payload={
            "telegram_user_id": telegram_user_id,
            "lead_id": lead_id,
            "is_duplicate": is_duplicate,
            "parse_status": parse_status,
        },
    )

    return {
        "telegram_join_id": join_id,
        "lead_id": lead_id,
        "is_duplicate": is_duplicate,
        "parse_status": parse_status,
        "source_account": parsed.source_account,
        "country_target": parsed.country_target,
        "campaign_id": parsed.campaign_id,
        "content_id": parsed.content_id,
        "content_attribution": content_attribution,
    }


def capture_telegram_start(
    *,
    telegram_user_id: int,
    telegram_username: Optional[str] = None,
    start_payload: Optional[str] = None,
    raw_payload: Optional[dict[str, Any]] = None,
    send_welcome: bool = True,
    notify_admin: bool = True,
) -> dict[str, Any]:
    """
    Agent 1 capture flow: /start → Supabase → welcome → admin alert.
    Logs Telegram failures to activity_logs without rolling back DB writes.
    """
    conn = get_connection()
    telegram_errors: list[str] = []

    try:
        result = upsert_telegram_join(
            conn,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            start_payload=start_payload,
            raw_payload=raw_payload,
        )
    except Exception as exc:
        log_activity(
            conn,
            entity_type="telegram_joins",
            entity_id=None,
            action="capture_start",
            status="failure",
            message="Database error during Telegram capture",
            actor="agent1-capture",
            source="telegram",
            error_detail=str(exc),
            payload={
                "telegram_user_id": telegram_user_id,
                "start_payload": start_payload,
            },
        )
        conn.close()
        raise

    result["telegram_user_id"] = telegram_user_id
    result["telegram_username"] = telegram_username

    # Import after DB work so capture works without Telegram env in tests
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from send_telegram_report import send_admin_join_alert, send_welcome_message

    if send_welcome:
        try:
            send_welcome_message(
                telegram_user_id,
                username=telegram_username,
                parse_status=result["parse_status"],
            )
            result["welcome_sent"] = True
        except Exception as exc:
            telegram_errors.append(f"welcome: {exc}")
            result["welcome_sent"] = False
            log_activity(
                conn,
                entity_type="telegram_joins",
                entity_id=result.get("telegram_join_id"),
                action="send_welcome",
                status="failure",
                message="Welcome message failed",
                actor="agent1-capture",
                source="telegram",
                error_detail=str(exc),
                payload={"telegram_user_id": telegram_user_id},
            )

    if notify_admin:
        try:
            send_admin_join_alert(result)
            result["admin_notified"] = True
        except Exception as exc:
            telegram_errors.append(f"admin: {exc}")
            result["admin_notified"] = False
            log_activity(
                conn,
                entity_type="telegram_joins",
                entity_id=result.get("telegram_join_id"),
                action="admin_notify",
                status="failure",
                message="Admin notification failed",
                actor="agent1-capture",
                source="telegram",
                error_detail=str(exc),
                payload=result,
            )

    if telegram_errors:
        result["telegram_error"] = "; ".join(telegram_errors)

    conn.close()
    return result


def cmd_health() -> int:
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM crm_stages")
            stage_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM activity_logs")
            log_count = cur.fetchone()[0]
        conn.close()
        print(json.dumps({
            "status": "healthy",
            "database_url_set": bool(DATABASE_URL),
            "supabase_url_set": bool(SUPABASE_URL),
            "crm_stages": stage_count,
            "activity_logs": log_count,
        }, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_test_join(payload: Optional[str]) -> int:
    fake_user_id = int(os.getenv("TEST_TELEGRAM_USER_ID", "999000001"))
    fake_username = os.getenv("TEST_TELEGRAM_USERNAME", "phase0_test_user")

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
        print(json.dumps({"status": "success", "result": result}, indent=2))
        return 0
    except Exception as exc:
        try:
            conn = get_connection()
            log_activity(
                conn,
                entity_type="telegram_joins",
                entity_id=None,
                action="test_join",
                status="failure",
                message="Test join failed",
                error_detail=str(exc),
            )
            conn.close()
        except Exception:
            pass
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_capture_start(
    user_id: int,
    username: Optional[str],
    payload: Optional[str],
    *,
    no_welcome: bool,
    no_admin: bool,
) -> int:
    try:
        result = capture_telegram_start(
            telegram_user_id=user_id,
            telegram_username=username,
            start_payload=payload,
            raw_payload={"source": "cli", "phase": "phase1"},
            send_welcome=not no_welcome,
            notify_admin=not no_admin,
        )
        print(json.dumps({"status": "success", "result": result}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_content_insert(args: argparse.Namespace) -> int:
    try:
        conn = get_connection()
        row = insert_content_performance(
            conn,
            content_id=args.content_id,
            post_url=args.post_url,
            source_post_url=args.source_post_url,
            x_account_id=args.x_account,
            country_target=args.country,
            campaign_id=args.campaign,
            hook=args.hook,
            angle=args.angle,
            hashtag=args.hashtag,
            clicks=args.clicks,
            views=args.views,
            likes=args.likes,
            status=args.status,
            notes=args.notes,
            raw_payload={"phase": "phase5", "test": True},
        )
        conn.close()
        print(json.dumps({"status": "success", "result": dict(row)}, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_content_metrics(args: argparse.Namespace) -> int:
    try:
        conn = get_connection()
        row = update_content_metrics(
            conn,
            args.content_id,
            views=args.views,
            likes=args.likes,
            replies=args.replies,
            reposts=args.reposts,
            clicks=args.clicks,
            telegram_joins=args.telegram_joins,
            status=args.status,
            notes=args.notes,
        )
        conn.close()
        print(json.dumps({"status": "success", "result": dict(row)}, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_content_mark_winning(content_id: str) -> int:
    try:
        conn = get_connection()
        row = mark_content_winning(conn, content_id)
        conn.close()
        print(json.dumps({"status": "success", "result": dict(row)}, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_content_test() -> int:
    """Phase 5 acceptance: insert → metrics → join attribution → winning."""
    try:
        conn = get_connection()
        insert_content_performance(
            conn,
            content_id="hook001",
            post_url="https://x.com/hermes_gold_uae/status/phase5test",
            source_post_url="https://x.com/source/demo",
            x_account_id="xacc_uae_001",
            country_target="uae",
            campaign_id="goldhook_20260624",
            hook="Gold breakout above 2350 — XAUUSD long setup",
            angle="breakout",
            hashtag="#xauusd",
            clicks=100,
            views=5000,
            likes=120,
            status="posted",
        )
        update_content_metrics(conn, "hook001", clicks=200, telegram_joins=3)
        upsert_telegram_join(
            conn,
            telegram_user_id=int(os.getenv("TEST_TELEGRAM_USER_ID", "999000003")),
            telegram_username="phase5_content_user",
            start_payload="src_xacc_uae_001_uae_goldhook_20260624_hook001",
            raw_payload={"phase": "phase5"},
        )
        mark_content_winning(conn, "hook001", notes="Phase 5 acceptance test")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content_id, telegram_joins, clicks, join_rate, status FROM content_performance WHERE content_id = %s",
                ("hook001",),
            )
            perf = cur.fetchone()
            cur.execute("SELECT status FROM content_assets WHERE id = %s", ("hook001",))
            asset_status = cur.fetchone()[0]
        conn.close()
        print(json.dumps({
            "status": "success",
            "content_performance": {
                "content_id": perf[0],
                "telegram_joins": perf[1],
                "clicks": perf[2],
                "join_rate": str(perf[3]),
                "status": perf[4],
            },
            "content_asset_status": asset_status,
        }, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync data to Supabase/Postgres")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Check database connectivity and table counts")

    test_parser = sub.add_parser("test-join", help="Insert a fake Telegram join for acceptance test")
    test_parser.add_argument(
        "--payload",
        default="src_xacc_uae_001_uae_goldhook_20260624",
        help="Telegram /start payload (without or with src_ prefix)",
    )

    capture = sub.add_parser("capture-start", help="Full Agent 1 flow: DB + welcome + admin")
    capture.add_argument("--user-id", type=int, required=True)
    capture.add_argument("--username", default=None)
    capture.add_argument("--payload", default=None, help="/start deep-link payload")
    capture.add_argument("--no-welcome", action="store_true", help="Skip welcome message")
    capture.add_argument("--no-admin", action="store_true", help="Skip admin notification")

    content_insert = sub.add_parser("content-insert", help="Insert posted content performance record")
    content_insert.add_argument("--content-id", required=True)
    content_insert.add_argument("--post-url")
    content_insert.add_argument("--source-post-url")
    content_insert.add_argument("--x-account")
    content_insert.add_argument("--country")
    content_insert.add_argument("--campaign")
    content_insert.add_argument("--hook")
    content_insert.add_argument("--angle")
    content_insert.add_argument("--hashtag")
    content_insert.add_argument("--clicks", type=int, default=0)
    content_insert.add_argument("--views", type=int, default=0)
    content_insert.add_argument("--likes", type=int, default=0)
    content_insert.add_argument("--status", default="posted")
    content_insert.add_argument("--notes")

    content_metrics = sub.add_parser("content-metrics", help="Update content performance metrics")
    content_metrics.add_argument("--content-id", required=True)
    content_metrics.add_argument("--views", type=int)
    content_metrics.add_argument("--likes", type=int)
    content_metrics.add_argument("--replies", type=int)
    content_metrics.add_argument("--reposts", type=int)
    content_metrics.add_argument("--clicks", type=int)
    content_metrics.add_argument("--telegram-joins", type=int)
    content_metrics.add_argument("--status")
    content_metrics.add_argument("--notes")

    content_win = sub.add_parser("content-mark-winning", help="Mark content as winning for reuse")
    content_win.add_argument("--content-id", required=True)

    sub.add_parser("content-test", help="Phase 5 acceptance test flow")

    args = parser.parse_args()

    if args.command == "health":
        return cmd_health()
    if args.command == "test-join":
        return cmd_test_join(args.payload)
    if args.command == "capture-start":
        return cmd_capture_start(
            args.user_id,
            args.username,
            args.payload,
            no_welcome=args.no_welcome,
            no_admin=args.no_admin,
        )

    if args.command == "content-insert":
        return cmd_content_insert(args)
    if args.command == "content-metrics":
        return cmd_content_metrics(args)
    if args.command == "content-mark-winning":
        return cmd_content_mark_winning(args.content_id)
    if args.command == "content-test":
        return cmd_content_test()

    return 1


if __name__ == "__main__":
    sys.exit(main())

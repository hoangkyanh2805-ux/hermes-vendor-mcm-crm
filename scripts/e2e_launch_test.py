#!/usr/bin/env python3
"""
MCM Vendor — Phase 9 E2E launch test (Agent 5).

Simulates the full Growth OS lead journey offline-first, then optional live checks.

Usage:
    python scripts/e2e_launch_test.py
    python scripts/e2e_launch_test.py --skip-external
    python scripts/e2e_launch_test.py --live-twenty --live-telegram
    python scripts/e2e_launch_test.py --report e2e-report.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

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
DATABASE_URL = os.getenv("DATABASE_URL", "")
E2E_USER_ID = int(os.getenv("E2E_TELEGRAM_USER_ID", "999009001"))
E2E_PAYLOAD = os.getenv(
    "E2E_START_PAYLOAD",
    "src_xacc_uae_001_uae_goldhook_20260624_e2e_hook001",
)


def run_script(args: list[str], timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        data: Any = None
        if stdout:
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                data = stdout[:2000]
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "data": data,
            "stderr": stderr[:500] if stderr else None,
        }
    except Exception as exc:
        return {"ok": False, "code": -1, "error": str(exc)}


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL)


def step_foundation() -> dict[str, Any]:
    r = run_script(["scripts/sync_to_supabase.py", "health"])
    healthy = r.get("ok") and isinstance(r.get("data"), dict) and r["data"].get("status") == "healthy"
    return {"pass": healthy, "detail": r}


def step_capture_join() -> dict[str, Any]:
    r = run_script(["scripts/sync_to_supabase.py", "test-join", "--payload", E2E_PAYLOAD])
    if not r.get("ok"):
        return {"pass": False, "detail": r}
    data = r.get("data") or {}
    result = data.get("result") or {}
    return {
        "pass": data.get("status") == "success" and bool(result.get("telegram_join_id") or result.get("lead_id")),
        "detail": r,
        "lead_id": result.get("lead_id"),
        "parse_status": result.get("parse_status"),
    }


def step_content_attribution() -> dict[str, Any]:
    r = run_script(["scripts/sync_to_supabase.py", "content-test"])
    return {"pass": r.get("ok"), "detail": r}


def step_crm_dry_run(live_twenty: bool) -> dict[str, Any]:
    if live_twenty and os.getenv("TWENTY_API_URL"):
        r = run_script([
            "scripts/sync_to_twenty.py", "sync-lead",
            "--telegram-user-id", str(E2E_USER_ID),
            "--live",
        ])
        return {"pass": r.get("ok"), "mode": "live", "detail": r}
    r = run_script(["scripts/sync_to_twenty.py", "test-sync", "--dry-run"])
    return {"pass": r.get("ok"), "mode": "dry-run", "detail": r}


def step_apify_intel() -> dict[str, Any]:
    r = run_script(["scripts/normalize_apify_dataset.py", "--sample", "--dry-run"])
    return {"pass": r.get("ok"), "detail": r}


def step_vendor_task() -> dict[str, Any]:
    r = run_script(["scripts/create_plane_task.py", "test"])
    return {"pass": r.get("ok"), "detail": r}


def step_automation() -> dict[str, Any]:
    r = run_script(["scripts/activepieces_webhook_test.py", "test"])
    return {"pass": r.get("ok"), "detail": r}


def step_bundle_verify() -> dict[str, Any]:
    r = run_script(["scripts/health_check.py", "bundle"])
    data = r.get("data") if isinstance(r.get("data"), dict) else {}
    complete = data.get("bundle_complete") is True
    return {"pass": r.get("ok") and complete, "detail": r}


def step_db_views() -> dict[str, Any]:
    views = [
        "v_growth_overview",
        "v_crm_stage_funnel",
        "v_content_performance",
        "v_winning_content",
        "v_purgatory_dashboard",
        "v_apify_crawl_health",
    ]
    try:
        conn = get_connection()
        missing = []
        with conn.cursor() as cur:
            for v in views:
                try:
                    cur.execute(f"SELECT 1 FROM {v} LIMIT 1")
                except Exception:
                    missing.append(v)
        conn.close()
        return {"pass": len(missing) == 0, "views_checked": views, "missing": missing}
    except Exception as exc:
        return {"pass": False, "error": str(exc)}


def step_activity_logs_clean() -> dict[str, Any]:
    """Fail only on non-test critical failures in last 24h."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT action, message, error_detail, actor, source
                FROM activity_logs
                WHERE status = 'failure'
                  AND created_at > NOW() - INTERVAL '24 hours'
                  AND COALESCE(error_detail, '') NOT ILIKE '%intentional test%'
                  AND COALESCE(message, '') NOT ILIKE '%acceptance%failure path%'
                  AND COALESCE(actor, '') NOT IN ('e2e_launch_test')
                ORDER BY created_at DESC
                LIMIT 20
                """
            )
            rows = cur.fetchall()
        conn.close()
        failures = [
            {"action": r[0], "message": r[1], "error": r[2], "actor": r[3], "source": r[4]}
            for r in rows
        ]
        return {"pass": len(failures) == 0, "critical_failures_24h": failures}
    except Exception as exc:
        return {"pass": False, "error": str(exc)}


def step_founder_report_dry() -> dict[str, Any]:
    r = run_script(["scripts/send_telegram_report.py", "founder-daily", "--dry-run"])
    text = str(r.get("data") or "")
    return {"pass": r.get("ok") and "MCM GROWTH OS" in text, "detail": r}


def step_health_overall() -> dict[str, Any]:
    r = run_script(["scripts/health_check.py"])
    data = r.get("data") if isinstance(r.get("data"), dict) else {}
    overall = data.get("overall", "unknown")
    return {
        "pass": overall in ("healthy", "degraded"),
        "overall": overall,
        "failed_services": data.get("failed_services", []),
        "detail": data,
    }


STEPS: list[tuple[str, str, Callable[..., dict[str, Any]]]] = [
    ("1_foundation", "Supabase health + schema", lambda **_: step_foundation()),
    ("2_capture", "Telegram join + attribution payload", lambda **_: step_capture_join()),
    ("3_content", "Content performance + join attribution", lambda **_: step_content_attribution()),
    ("4_crm", "Twenty CRM sync", lambda live_twenty=False, **_: step_crm_dry_run(live_twenty)),
    ("5_intelligence", "Apify normalize sample", lambda **_: step_apify_intel()),
    ("6_vendor", "Plane vendor_tasks", lambda **_: step_vendor_task()),
    ("7_automation", "Activepieces acceptance", lambda **_: step_automation()),
    ("8_views", "Dashboard SQL views", lambda **_: step_db_views()),
    ("9_monitor", "Health check + bundle", lambda **_: step_bundle_verify()),
    ("10_rhythm", "Founder report dry-run", lambda **_: step_founder_report_dry()),
    ("11_activity_logs", "No critical failures 24h", lambda **_: step_activity_logs_clean()),
    ("12_stack_health", "Overall stack health", lambda **_: step_health_overall()),
]


def run_e2e(
    *,
    live_twenty: bool = False,
    skip_external: bool = False,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    results: dict[str, Any] = {}
    passed = 0
    failed = 0
    skipped = 0

    for step_id, label, fn in STEPS:
        if skip_external and step_id in ("4_crm",) and not live_twenty:
            if not DATABASE_URL:
                results[step_id] = {"label": label, "status": "skipped", "reason": "no DATABASE_URL"}
                skipped += 1
                continue

        t0 = time.perf_counter()
        try:
            outcome = fn(live_twenty=live_twenty)
            ok = outcome.get("pass") is True
            status = "pass" if ok else "fail"
            if ok:
                passed += 1
            else:
                failed += 1
            results[step_id] = {
                "label": label,
                "status": status,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                **{k: v for k, v in outcome.items() if k != "pass"},
            }
        except Exception as exc:
            failed += 1
            results[step_id] = {
                "label": label,
                "status": "fail",
                "error": str(exc),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }

    total = passed + failed + skipped
    return {
        "test": "mcm_growth_os_e2e",
        "phase": "phase9",
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "launch_ready": failed == 0 and DATABASE_URL,
        },
        "e2e_user_id": E2E_USER_ID,
        "e2e_payload": E2E_PAYLOAD,
        "steps": results,
        "rollback_plan": "docs/rollback-plan.md",
        "next": "Phase 10 bundle complete — README, case-study-mapping, CLAUDE.md",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 9 E2E launch test")
    parser.add_argument("--skip-external", action="store_true", help="Skip steps needing external APIs")
    parser.add_argument("--live-twenty", action="store_true", help="Live Twenty sync for step 4")
    parser.add_argument("--report", help="Write JSON report to file")
    args = parser.parse_args()

    if not DATABASE_URL:
        print(json.dumps({
            "status": "error",
            "message": "DATABASE_URL required for E2E. Use docker compose up -d then set .env",
        }, indent=2))
        return 1

    report = run_e2e(live_twenty=args.live_twenty, skip_external=args.skip_external)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(json.dumps(report, indent=2, default=str))
    return 0 if report["summary"]["launch_ready"] else 1


if __name__ == "__main__":
    sys.exit(main())

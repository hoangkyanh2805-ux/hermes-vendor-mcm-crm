#!/usr/bin/env python3
"""
MCM Vendor — Agent 5 health check + operating rhythm (Phase 8).

Usage:
    python scripts/health_check.py
    python scripts/health_check.py --persist
    python scripts/health_check.py bundle
    python scripts/health_check.py founder-data
    python scripts/health_check.py weekly-review
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
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
DATABASE_URL = os.getenv("DATABASE_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
METABASE_URL = os.getenv("METABASE_URL", "").rstrip("/")
GITHUB_MONITOR_ENABLED = os.getenv("GITHUB_MONITOR_ENABLED", "auto")


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL)


def check_env(keys: list[str]) -> dict[str, bool]:
    return {k: bool(os.getenv(k)) for k in keys}


def run_script(args: list[str], timeout: int = 45) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                return {"status": "ok", "data": json.loads(proc.stdout)}
            except json.JSONDecodeError:
                return {"status": "ok", "raw": proc.stdout.strip()[:500]}
        return {
            "status": "error",
            "code": proc.returncode,
            "stderr": (proc.stderr or proc.stdout or "")[:500],
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def timed_check(name: str, fn) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        result = fn()
        latency = int((time.perf_counter() - start) * 1000)
        if result.get("status") == "ok" or result.get("healthy") is True:
            return {
                "service_name": name,
                "status": "healthy",
                "latency_ms": latency,
                "message": result.get("message", "ok"),
                "details": result,
            }
        if result.get("status") == "skipped":
            return {
                "service_name": name,
                "status": "unknown",
                "latency_ms": latency,
                "message": result.get("message", "not configured"),
                "details": result,
            }
        return {
            "service_name": name,
            "status": "degraded" if result.get("partial") else "down",
            "latency_ms": latency,
            "message": result.get("message") or result.get("stderr") or "check failed",
            "details": result,
        }
    except Exception as exc:
        latency = int((time.perf_counter() - start) * 1000)
        return {
            "service_name": name,
            "status": "down",
            "latency_ms": latency,
            "message": str(exc),
            "details": {},
        }


def check_hermes() -> dict[str, Any]:
    skills = list((ROOT / "skills").glob("agent*.yaml"))
    env_ok = bool(os.getenv("APP_BASE_URL") or os.getenv("HERMES_WEBHOOK_SECRET"))
    if len(skills) >= 5 and env_ok:
        return {"status": "ok", "message": f"{len(skills)} skills loaded", "skills": [s.name for s in skills]}
    if len(skills) >= 5:
        return {"status": "ok", "message": f"{len(skills)} skills (env partial)", "partial": True}
    return {"status": "error", "message": f"Expected 5 skills, found {len(skills)}"}


def check_telegram() -> dict[str, Any]:
    if not TELEGRAM_BOT_TOKEN:
        return {"status": "skipped", "message": "TELEGRAM_BOT_TOKEN not set"}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("ok"):
            return {"status": "ok", "message": f"@{data['result'].get('username', 'bot')}"}
        return {"status": "error", "message": str(data)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def check_metabase() -> dict[str, Any]:
    if not METABASE_URL:
        return {"status": "skipped", "message": "METABASE_URL not set"}
    try:
        req = urllib.request.Request(f"{METABASE_URL}/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"status": "ok" if resp.status < 400 else "error", "message": f"HTTP {resp.status}"}
    except Exception:
        try:
            with urllib.request.urlopen(METABASE_URL, timeout=10) as resp:
                return {"status": "ok", "message": f"HTTP {resp.status} (root)"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}


def check_vps() -> dict[str, Any]:
    try:
        import psutil  # type: ignore
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory().percent
        status = "ok" if cpu < 90 and mem < 90 else "error"
        return {
            "status": status,
            "message": f"CPU {cpu}% MEM {mem}%",
            "cpu_percent": cpu,
            "mem_percent": mem,
            "partial": cpu >= 80 or mem >= 80,
        }
    except ImportError:
        return {"status": "skipped", "message": "psutil not installed — VPS load monitoring documented only"}


def check_github() -> dict[str, Any]:
    if GITHUB_MONITOR_ENABLED == "false":
        return {"status": "skipped", "message": "GITHUB_MONITOR_ENABLED=false"}
    if shutil.which("git") and (ROOT / ".git").exists():
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--format=%h %s (%cr)"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(ROOT),
            )
            if proc.returncode == 0:
                return {"status": "ok", "message": proc.stdout.strip(), "last_commit": proc.stdout.strip()}
            return {"status": "error", "message": proc.stderr.strip() or "git log failed"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
    return {
        "status": "skipped",
        "message": "GitHub commit monitoring pending — no .git repo or git CLI (documented)",
    }


def build_health_report() -> dict[str, Any]:
    checks = {
        "hermes": check_hermes,
        "supabase": lambda: run_script(["scripts/sync_to_supabase.py", "health"]),
        "telegram": check_telegram,
        "twenty": lambda: run_script(["scripts/sync_to_twenty.py", "health"]),
        "apify": lambda: run_script(["scripts/run_apify_crawl.py", "health"]),
        "metabase": check_metabase,
        "plane": lambda: run_script(["scripts/create_plane_task.py", "health"]),
        "activepieces": lambda: run_script(["scripts/activepieces_webhook_test.py", "health"]),
        "vps": check_vps,
        "github": check_github,
    }

    services = {name: timed_check(name, fn) for name, fn in checks.items()}

    failed = [s for s in services.values() if s["status"] in ("down", "degraded")]
    overall = "healthy"
    if any(s["status"] == "down" for s in services.values()):
        overall = "down"
    elif failed:
        overall = "degraded"

    automation_failures = 0
    if DATABASE_URL and psycopg2:
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM activity_logs
                    WHERE status = 'failure' AND created_at > NOW() - INTERVAL '24 hours'
                    """
                )
                automation_failures = cur.fetchone()[0]
            conn.close()
        except Exception:
            pass

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "services": services,
        "failed_services": [s["service_name"] for s in failed],
        "automation_failures_24h": automation_failures,
        "env": check_env([
            "DATABASE_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_CHAT_ID",
            "TWENTY_API_URL", "APIFY_API_TOKEN", "PLANE_API_URL", "ACTIVEPIECES_API_URL",
        ]),
    }


def persist_health_logs(report: dict[str, Any]) -> int:
    conn = get_connection()
    count = 0
    with conn.cursor() as cur:
        for svc in report["services"].values():
            cur.execute(
                """
                INSERT INTO system_health_logs (service_name, status, latency_ms, message, details)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    svc["service_name"],
                    svc["status"] if svc["status"] in ("healthy", "degraded", "down", "unknown") else "unknown",
                    svc.get("latency_ms"),
                    svc.get("message"),
                    json.dumps(svc.get("details") or {}),
                ),
            )
            count += 1
    conn.commit()
    conn.close()
    return count


def _fetchone_dict(cur, query: str, params: tuple = ()) -> dict[str, Any]:
    cur.execute(query, params)
    row = cur.fetchone()
    if not row:
        return {}
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def fetch_founder_report_data(conn) -> dict[str, Any]:
    today = date.today()
    data: dict[str, Any] = {"report_date": today.isoformat()}

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM telegram_joins WHERE DATE(join_time) = %s",
            (today,),
        )
        data["telegram_joins_today"] = cur.fetchone()[0]

        try:
            overview = _fetchone_dict(cur, "SELECT * FROM v_growth_overview LIMIT 1")
            data.update({
                "top_country": overview.get("top_country_30d"),
                "top_x_account": overview.get("top_x_account_30d"),
                "top_vendor": overview.get("top_vendor_30d"),
                "cost_per_join": overview.get("avg_cost_per_join"),
            })
        except Exception:
            pass

        cur.execute("SELECT stage_name, lead_count, avg_days_in_stage FROM v_crm_stage_funnel")
        funnel = {r[0]: {"count": r[1], "avg_days": r[2]} for r in cur.fetchall()}
        data["crm_funnel"] = funnel
        data["stage_new_x_visitor"] = funnel.get("New X Visitor", {}).get("count", 0)
        data["stage_telegram_joined"] = funnel.get("Telegram Joined", {}).get("count", 0)
        data["stage_warm_member"] = funnel.get("Warm Member", {}).get("count", 0)
        data["stage_signal_interested"] = funnel.get("Signal Interested", {}).get("count", 0)
        data["stage_paid_vip"] = funnel.get("Paid / VIP", {}).get("count", 0)
        data["stage_renewal_risk"] = funnel.get("Renewal Risk", {}).get("count", 0)

        bottleneck = max(funnel.items(), key=lambda x: x[1].get("avg_days") or 0, default=(None, {}))
        data["crm_bottleneck"] = (
            f"{bottleneck[0]} ({bottleneck[1].get('avg_days', 0)}d avg)" if bottleneck[0] else "N/A"
        )

        cur.execute("SELECT COUNT(*) FROM content_performance WHERE status IN ('posted', 'tracked', 'winning')")
        data["posts_tracked"] = cur.fetchone()[0]

        cur.execute(
            """
            SELECT hook FROM content_performance
            WHERE status = 'winning' ORDER BY join_rate DESC NULLS LAST LIMIT 1
            """
        )
        row = cur.fetchone()
        data["winning_hook"] = row[0] if row else None

        cur.execute(
            """
            SELECT hashtag FROM content_performance
            WHERE hashtag IS NOT NULL GROUP BY hashtag ORDER BY SUM(telegram_joins) DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        data["top_hashtag"] = row[0] if row else None

        cur.execute(
            """
            SELECT angle FROM content_performance
            WHERE angle IS NOT NULL GROUP BY angle ORDER BY SUM(telegram_joins) DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        data["best_content_angle"] = row[0] if row else None

        try:
            apify = _fetchone_dict(
                cur,
                "SELECT * FROM v_apify_crawl_health ORDER BY last_crawl_at DESC NULLS LAST LIMIT 1",
            )
            data["apify_run_status"] = "healthy" if apify else "no data"
            data["apify_posts_crawled"] = apify.get("posts_crawled", 0)
            data["apify_high_potential"] = apify.get("high_potential_posts", 0)
            data["apify_top_country"] = apify.get("top_country")
            data["apify_error"] = None
        except Exception as exc:
            data["apify_run_status"] = "error"
            data["apify_error"] = str(exc)

        cur.execute(
            "SELECT COUNT(*) FROM vendor_tasks WHERE DATE(created_at) = %s", (today,)
        )
        data["vendor_tasks_created"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM vendor_tasks WHERE status = 'posted'")
        data["vendor_tasks_posted"] = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM vendor_tasks WHERE status IN ('assigned', 'ready_to_post') AND deadline < NOW()"
        )
        data["vendor_tasks_overdue"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM vendor_tasks WHERE status = 'need_fix'")
        data["vendor_tasks_need_fix"] = cur.fetchone()[0]

        cur.execute(
            """
            SELECT alert_type, COUNT(*) FROM v_purgatory_dashboard
            GROUP BY alert_type
            """
        )
        data["purgatory"] = dict(cur.fetchall())

        cur.execute(
            """
            SELECT action, message FROM activity_logs
            WHERE status = 'failure' AND created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC LIMIT 5
            """
        )
        data["recent_failures"] = [{"action": r[0], "message": r[1]} for r in cur.fetchall()]

    data["action_items"] = build_action_items(data)
    return data


def build_action_items(data: dict[str, Any]) -> list[str]:
    items: list[str] = []
    purgatory = data.get("purgatory") or {}
    if purgatory.get("vendor_overdue", 0) > 0:
        items.append(f"Clear {purgatory['vendor_overdue']} overdue vendor tasks")
    if purgatory.get("inactive_member", 0) > 0:
        items.append(f"Nurture {purgatory['inactive_member']} inactive members")
    if purgatory.get("stuck_stage", 0) > 0:
        items.append(f"Review {purgatory['stuck_stage']} leads stuck in stage")
    if data.get("vendor_tasks_overdue", 0) > 0:
        items.append("Follow up Plane board overdue column")
    if data.get("recent_failures"):
        items.append(f"Fix automation: {data['recent_failures'][0].get('action', 'unknown')}")
    if len(items) < 3:
        items.append("Review winning content for repurpose")
    if len(items) < 3:
        items.append("Check Apify intel for tomorrow's posts")
    return items[:3]


def format_founder_daily_report(data: dict[str, Any], health: dict[str, Any]) -> str:
    d = data.get("report_date", date.today().isoformat())
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>MCM GROWTH OS — {d}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "<b>1. Growth</b>",
        f"- Telegram joins today: <b>{data.get('telegram_joins_today', 0)}</b>",
        f"- Top country: <code>{data.get('top_country') or 'N/A'}</code>",
        f"- Top X account: <code>{data.get('top_x_account') or 'N/A'}</code>",
        f"- Top vendor: <code>{data.get('top_vendor') or 'N/A'}</code>",
        f"- Cost/join: <code>{data.get('cost_per_join') or 'N/A'}</code>",
        "",
        "<b>2. CRM</b>",
        f"- New X Visitor: {data.get('stage_new_x_visitor', 0)}",
        f"- Telegram Joined: {data.get('stage_telegram_joined', 0)}",
        f"- Warm Member: {data.get('stage_warm_member', 0)}",
        f"- Signal Interested: {data.get('stage_signal_interested', 0)}",
        f"- Paid/VIP: {data.get('stage_paid_vip', 0)}",
        f"- Renewal Risk: {data.get('stage_renewal_risk', 0)}",
        f"- Bottleneck: {data.get('crm_bottleneck', 'N/A')}",
        "",
        "<b>3. Content</b>",
        f"- Posts tracked: {data.get('posts_tracked', 0)}",
        f"- Winning hook: {data.get('winning_hook') or 'N/A'}",
        f"- Top hashtag: <code>{data.get('top_hashtag') or 'N/A'}</code>",
        f"- Best content angle: <code>{data.get('best_content_angle') or 'N/A'}</code>",
        "",
        "<b>4. Apify Intelligence</b>",
        f"- Run status: <code>{data.get('apify_run_status', 'N/A')}</code>",
        f"- Posts crawled: {data.get('apify_posts_crawled', 0)}",
        f"- High potential posts: {data.get('apify_high_potential', 0)}",
        f"- Top country: <code>{data.get('apify_top_country') or 'N/A'}</code>",
        f"- Error: {data.get('apify_error') or 'none'}",
        "",
        "<b>5. Vendor Ops</b>",
        f"- Tasks created: {data.get('vendor_tasks_created', 0)}",
        f"- Tasks posted: {data.get('vendor_tasks_posted', 0)}",
        f"- Overdue: <b>{data.get('vendor_tasks_overdue', 0)}</b>",
        f"- Need fix: {data.get('vendor_tasks_need_fix', 0)}",
        "",
        "<b>6. System Health</b>",
        f"- Overall: <b>{health.get('overall', 'unknown').upper()}</b>",
    ]

    for name, svc in (health.get("services") or {}).items():
        st = svc.get("status", "unknown")
        icon = "✅" if st == "healthy" else ("⚠️" if st in ("degraded", "unknown") else "❌")
        label = name.capitalize()
        if st in ("down", "degraded"):
            label = f"<b>{label} — FAILED</b>"
        lines.append(f"- {icon} {label}: {st} — {svc.get('message', '')[:60]}")

    lines.extend(["", "<b>7. Action Items Tomorrow</b>"])
    for i, item in enumerate(data.get("action_items") or ["Review dashboard"], 1):
        lines.append(f"{i}. {item}")

    if health.get("failed_services"):
        lines.extend(["", f"⚠️ <b>Failed:</b> {', '.join(health['failed_services'])}"])

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def build_weekly_review(conn) -> dict[str, Any]:
    since = date.today() - timedelta(days=7)
    review: dict[str, Any] = {"week_ending": date.today().isoformat(), "since": since.isoformat()}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT country_target, COUNT(*) AS joins FROM leads
            WHERE join_time >= %s GROUP BY country_target ORDER BY joins DESC LIMIT 1
            """,
            (since,),
        )
        row = cur.fetchone()
        review["top_winning_country"] = row[0] if row else None

        cur.execute(
            """
            SELECT hook FROM content_performance
            WHERE posted_at >= %s AND hook IS NOT NULL
            ORDER BY telegram_joins DESC, join_rate DESC LIMIT 1
            """,
            (since,),
        )
        row = cur.fetchone()
        review["top_winning_hook"] = row[0] if row else None

        cur.execute(
            """
            SELECT v.name, COUNT(l.id) AS leads FROM leads l
            JOIN vendors v ON v.id = l.vendor_id
            WHERE l.join_time >= %s GROUP BY v.name ORDER BY leads DESC LIMIT 1
            """,
            (since,),
        )
        row = cur.fetchone()
        review["top_winning_vendor"] = row[0] if row else None

        cur.execute("SELECT stage_name, lead_count, avg_days_in_stage FROM v_crm_stage_funnel")
        funnel = cur.fetchall()
        if funnel:
            weakest = max(funnel, key=lambda r: r[2] or 0)
            review["weakest_stage"] = f"{weakest[0]} ({weakest[2]}d avg)"

        cur.execute(
            """
            SELECT DATE(join_time) AS d, COUNT(*) FROM telegram_joins
            WHERE join_time >= %s GROUP BY DATE(join_time) ORDER BY d
            """,
            (since,),
        )
        daily = cur.fetchall()
        review["joins_by_day"] = {str(r[0]): r[1] for r in daily}
        if len(daily) >= 2:
            review["cost_per_join_trend"] = "see v_campaign_performance / daily_kpis"
        else:
            review["cost_per_join_trend"] = "insufficient data"

        cur.execute(
            "SELECT content_id, hook, join_rate FROM v_winning_content LIMIT 3"
        )
        review["content_to_repeat"] = [
            {"content_id": r[0], "hook": r[1], "join_rate": str(r[2])} for r in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT xa.handle FROM x_accounts xa
            WHERE xa.status = 'active'
              AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.source_account = xa.id AND l.join_time >= %s)
            LIMIT 5
            """,
            (since,),
        )
        review["accounts_to_pause"] = [r[0] for r in cur.fetchall()]

    review["next_week_priority"] = build_action_items(fetch_founder_report_data(conn))
    return review


def format_weekly_review(review: dict[str, Any]) -> str:
    lines = [
        "<b>MCM WEEKLY REVIEW</b>",
        f"Week ending: {review.get('week_ending')}",
        "",
        f"Top winning country: <code>{review.get('top_winning_country') or 'N/A'}</code>",
        f"Top winning hook: {review.get('top_winning_hook') or 'N/A'}",
        f"Top winning vendor: <code>{review.get('top_winning_vendor') or 'N/A'}</code>",
        f"Weakest stage: {review.get('weakest_stage') or 'N/A'}",
        f"Cost/join trend: {review.get('cost_per_join_trend', 'N/A')}",
        "",
        "<b>Content to repeat:</b>",
    ]
    for c in review.get("content_to_repeat") or []:
        lines.append(f"• {c.get('hook', '')[:50]} (rate {c.get('join_rate')})")
    lines.extend(["", "<b>Accounts to pause:</b>"])
    for a in review.get("accounts_to_pause") or []:
        lines.append(f"• @{a}")
    if not review.get("accounts_to_pause"):
        lines.append("• none flagged")
    lines.extend(["", "<b>Next week priority:</b>"])
    for i, p in enumerate(review.get("next_week_priority") or [], 1):
        lines.append(f"{i}. {p}")
    return "\n".join(lines)


def check_bundle_files() -> dict[str, bool]:
    required = [
        "README.md", "CLAUDE.md",
        "docs/bundle-manifest.md", "docs/sop-ops.md", "docs/runbook.md",
        "docs/master-plan.md", "docs/launch-checklist.md", "docs/rollback-plan.md",
        "docs/case-study-mapping.md",
        "skills/agent1-capture.yaml", "skills/agent2-onboard.yaml",
        "skills/agent3-daily-loop.yaml",
        "skills/agent4-twenty-crm-sync.yaml", "skills/agent5-monitor.yaml",
        "config/twenty-pipeline.json", "config/metabase-dashboard-spec.md",
        "config/apify-xauusd-crawl.json", "config/plane-board-spec.md",
        "config/activepieces-flows-spec.md", "prompts/report-founder.txt",
        "scripts/e2e_launch_test.py",
        "db/schema.sql",
    ]
    return {p: (ROOT / p).exists() for p in required}


def main() -> int:
    args = sys.argv[1:]

    if args and args[0] == "bundle":
        files = check_bundle_files()
        missing = [k for k, v in files.items() if not v]
        print(json.dumps({"bundle_complete": len(missing) == 0, "files": files, "missing": missing}, indent=2))
        return 0 if not missing else 1

    if args and args[0] == "founder-data":
        health = build_health_report()
        try:
            conn = get_connection()
            data = fetch_founder_report_data(conn)
            conn.close()
            print(json.dumps({"health": health, "metrics": data}, indent=2, default=str))
        except Exception as exc:
            print(json.dumps({"health": health, "metrics_error": str(exc)}, indent=2))
        return 0

    if args and args[0] == "weekly-review":
        try:
            conn = get_connection()
            review = build_weekly_review(conn)
            conn.close()
            print(json.dumps({
                "review": review,
                "formatted": format_weekly_review(review),
            }, indent=2, default=str))
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
            return 1
        return 0

    persist = "--persist" in args
    report = build_health_report()

    if persist and DATABASE_URL:
        try:
            report["persisted_rows"] = persist_health_logs(report)
        except Exception as exc:
            report["persist_error"] = str(exc)

    print(json.dumps(report, indent=2))
    return 0 if report["overall"] != "down" else 1


if __name__ == "__main__":
    sys.exit(main())

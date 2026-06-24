#!/usr/bin/env python3
"""
MCM Vendor — Hermes XAUUSD Growth OS v2
Phase 6: Create Plane vendor/content tasks + mirror vendor_tasks.

Usage:
    python scripts/create_plane_task.py health
    python scripts/create_plane_task.py list-states
    python scripts/create_plane_task.py create --country UAE --hashtag "#xauusd" --angle breakout --dry-run
    python scripts/create_plane_task.py from-apify --dry-run
    python scripts/create_plane_task.py from-winning --content-id hook001 --dry-run
    python scripts/create_plane_task.py sync-status --vendor-task-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
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
BOARD_CONFIG = ROOT / "config" / "plane-board.json"

PLANE_API_URL = os.getenv("PLANE_API_URL", "https://api.plane.so").rstrip("/")
PLANE_API_KEY = os.getenv("PLANE_API_KEY", "")
PLANE_WORKSPACE_ID = os.getenv("PLANE_WORKSPACE_ID", "")
PLANE_PROJECT_ID = os.getenv("PLANE_PROJECT_ID", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "")


@dataclass
class TaskSpec:
    country_target: str
    hashtag: str
    angle: str
    hook: Optional[str] = None
    source_post_url: Optional[str] = None
    x_account_id: Optional[str] = None
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    campaign_id: Optional[str] = None
    content_id: Optional[str] = None
    expected_output: str = "1 X post + BioLink/Telegram link update"
    deadline: Optional[str] = None
    cta: str = "Join Telegram for daily XAUUSD gold setups"
    biolink: Optional[str] = None
    acceptance_criteria: str = "Posted on X; join tracked in Supabase via deep link"
    status: str = "backlog"
    source: str = "manual"
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return f"[{self.country_target}] {self.hashtag} {self.angle}"

    def build_description_html(self) -> str:
        biolink = self.biolink or self._default_biolink()
        lines = [
            "<h3>MCM Vendor Content Task</h3>",
            "<ul>",
            f"<li><b>Country:</b> {self.country_target}</li>",
            f"<li><b>Hashtag:</b> {self.hashtag}</li>",
            f"<li><b>Angle:</b> {self.angle}</li>",
            f"<li><b>Hook:</b> {self.hook or 'N/A'}</li>",
            f"<li><b>Source post URL:</b> {self.source_post_url or 'N/A'}</li>",
            f"<li><b>Target account group:</b> {self.x_account_id or 'N/A'}</li>",
            f"<li><b>Vendor:</b> {self.vendor_name or self.vendor_id or 'N/A'}</li>",
            f"<li><b>Expected output:</b> {self.expected_output}</li>",
            f"<li><b>Deadline:</b> {self.deadline or 'N/A'}</li>",
            f"<li><b>CTA:</b> {self.cta}</li>",
            f"<li><b>BioLink/Telegram:</b> {biolink}</li>",
            f"<li><b>Acceptance criteria:</b> {self.acceptance_criteria}</li>",
            f"<li><b>Source:</b> {self.source}</li>",
            "</ul>",
        ]
        return "\n".join(lines)

    def _default_biolink(self) -> str:
        account = self.x_account_id or "xacc"
        country = (self.country_target or "unknown").lower().replace(" ", "")
        campaign = self.campaign_id or "campaign"
        content = self.content_id or "content"
        return f"https://t.me/hermes7979_bot?start=src_{account}_{country}_{campaign}_{content}"


def load_board_config() -> dict[str, Any]:
    with open(BOARD_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL)


def log_activity(conn, **kwargs) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO activity_logs (entity_type, entity_id, action, status, message, actor, source, error_detail, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                kwargs.get("entity_type", "vendor_tasks"),
                kwargs.get("entity_id"),
                kwargs.get("action", "create"),
                kwargs.get("status", "success"),
                kwargs.get("message"),
                kwargs.get("actor", "create_plane_task"),
                kwargs.get("source", "plane"),
                kwargs.get("error_detail"),
                json.dumps(kwargs.get("payload") or {}),
            ),
        )
    conn.commit()


def plane_request(method: str, path: str, body: Optional[dict[str, Any]] = None) -> Any:
    if not PLANE_API_KEY:
        raise RuntimeError("PLANE_API_KEY is not set")
    url = f"{PLANE_API_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "X-API-Key": PLANE_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Plane API {exc.code} {method} {path}: {detail}") from exc


def api_path(template_key: str) -> str:
    config = load_board_config()
    tpl = config["api_paths"][template_key]
    return tpl.format(workspace=PLANE_WORKSPACE_ID, project_id=PLANE_PROJECT_ID)


def resolve_state_id(status: str) -> Optional[str]:
    env_key = f"PLANE_STATE_{status.upper()}"
    if os.getenv(env_key):
        return os.getenv(env_key)
    for col in load_board_config().get("columns", []):
        if col.get("vendor_status") == status and col.get("plane_state_id"):
            return col["plane_state_id"]
    return None


def create_plane_work_item(spec: TaskSpec, *, dry_run: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": spec.title,
        "description_html": spec.build_description_html(),
        "priority": "medium",
    }
    state_id = resolve_state_id(spec.status)
    if state_id:
        body["state_id"] = state_id

    if dry_run:
        return {"dry_run": True, "endpoint": api_path("work_items"), "body": body}

    if not PLANE_WORKSPACE_ID or not PLANE_PROJECT_ID:
        raise RuntimeError("PLANE_WORKSPACE_ID and PLANE_PROJECT_ID must be set")

    for key in ("work_items", "issues_legacy"):
        try:
            resp = plane_request("POST", api_path(key), body)
            data = resp if isinstance(resp, dict) else {}
            plane_id = data.get("id") or (data.get("data") or {}).get("id")
            if plane_id:
                return {"plane_task_id": plane_id, "api": key, "response": resp}
        except RuntimeError as exc:
            last_err = exc
            if key == "issues_legacy":
                raise
    raise RuntimeError(f"Plane create failed: {last_err}")


def insert_vendor_task(conn, spec: TaskSpec, plane_task_id: Optional[str]) -> str:
    deadline = None
    if spec.deadline:
        try:
            deadline = datetime.fromisoformat(spec.deadline.replace("Z", "+00:00"))
        except ValueError:
            deadline = datetime.strptime(spec.deadline, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO vendor_tasks (
                plane_task_id, title, description, country_target, hashtag, angle, hook,
                source_post_url, vendor_id, content_id, status, deadline, raw_payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                plane_task_id,
                spec.title,
                spec.build_description_html(),
                spec.country_target,
                spec.hashtag,
                spec.angle,
                spec.hook,
                spec.source_post_url,
                spec.vendor_id,
                spec.content_id,
                spec.status,
                deadline,
                json.dumps({**spec.raw_payload, "source": spec.source}),
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return str(row[0])


def create_task(spec: TaskSpec, *, dry_run: bool = False, skip_plane: bool = False) -> dict[str, Any]:
    plane_result: dict[str, Any] = {}
    plane_task_id = None

    if not skip_plane:
        plane_result = create_plane_work_item(spec, dry_run=dry_run)
        plane_task_id = plane_result.get("plane_task_id")

    if dry_run:
        return {
            "status": "dry_run",
            "spec": {"title": spec.title, "status": spec.status, "source": spec.source},
            "plane": plane_result,
        }

    conn = get_connection()
    try:
        vendor_task_id = insert_vendor_task(conn, spec, plane_task_id)
        log_activity(
            conn,
            entity_type="vendor_tasks",
            entity_id=vendor_task_id,
            action="create",
            message=f"Vendor task created: {spec.title}",
            payload={"plane_task_id": plane_task_id, "source": spec.source},
        )
    except Exception as exc:
        log_activity(
            conn,
            entity_type="vendor_tasks",
            entity_id=None,
            action="create",
            status="failure",
            message="Failed to insert vendor_tasks",
            error_detail=str(exc),
            payload={"title": spec.title},
        )
        raise
    finally:
        conn.close()

    return {
        "status": "success",
        "vendor_task_id": vendor_task_id,
        "plane_task_id": plane_task_id,
        "title": spec.title,
        "plane": plane_result,
    }


def task_from_apify_row(row: dict[str, Any]) -> TaskSpec:
    country = row.get("country_target") or "unknown"
    hashtag = row.get("hashtag") or "#xauusd"
    return TaskSpec(
        country_target=country,
        hashtag=hashtag,
        angle=row.get("content_angle") or "gold",
        hook=row.get("hook_extracted") or (row.get("post_text") or "")[:120],
        source_post_url=row.get("post_url"),
        status="backlog",
        source="apify_high_potential",
        raw_payload={"apify_post_id": str(row.get("id")), "lead_potential": row.get("lead_potential")},
    )


def fetch_high_potential_apify(conn, limit: int = 1) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM apify_posts
            WHERE lead_potential = 'High'
            ORDER BY engagement_score DESC, created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_winning_content(conn, content_id: str) -> Optional[dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT cp.*, xa.id AS x_account_id, c.id AS campaign_id
            FROM content_performance cp
            LEFT JOIN x_accounts xa ON xa.id = cp.x_account_id
            LEFT JOIN campaigns c ON c.id = cp.campaign_id
            WHERE cp.content_id = %s
            """,
            (content_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def sync_vendor_task_status(conn, vendor_task_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM vendor_tasks WHERE id = %s", (vendor_task_id,))
        task = cur.fetchone()
    if not task:
        raise ValueError("vendor_task not found")
    task = dict(task)
    plane_id = task.get("plane_task_id")
    if not plane_id:
        return {"status": "skipped", "reason": "no plane_task_id — local only task"}

    if dry_run:
        return {"status": "dry_run", "would_sync": plane_id, "vendor_task_id": vendor_task_id}

    path = f"{api_path('work_items')}{plane_id}/"
    try:
        item = plane_request("GET", path)
    except RuntimeError:
        path = f"{api_path('issues_legacy')}{plane_id}/"
        item = plane_request("GET", path)

    data = item.get("data", item) if isinstance(item, dict) else item
    state_id = data.get("state_id") or data.get("state")
    new_status = task["status"]
    for col in load_board_config().get("columns", []):
        if col.get("plane_state_id") and col["plane_state_id"] == state_id:
            new_status = col["vendor_status"]
            break

    if new_status != task["status"]:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vendor_tasks SET status = %s, updated_at = NOW() WHERE id = %s",
                (new_status, vendor_task_id),
            )
        conn.commit()
        log_activity(
            conn,
            entity_type="vendor_tasks",
            entity_id=vendor_task_id,
            action="sync_status",
            message=f"Status synced from Plane: {task['status']} → {new_status}",
            payload={"plane_task_id": plane_id, "state_id": state_id},
        )

    return {
        "status": "success",
        "vendor_task_id": vendor_task_id,
        "plane_task_id": plane_id,
        "old_status": task["status"],
        "new_status": new_status,
        "state_id": state_id,
    }


def cmd_health() -> int:
    out: dict[str, Any] = {
        "plane_api_url": PLANE_API_URL,
        "api_key_set": bool(PLANE_API_KEY),
        "workspace_set": bool(PLANE_WORKSPACE_ID),
        "project_set": bool(PLANE_PROJECT_ID),
        "database_url_set": bool(DATABASE_URL),
        "board": load_board_config().get("board_name"),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_list_states() -> int:
    try:
        resp = plane_request("GET", api_path("states"))
        print(json.dumps(resp, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_create(args: argparse.Namespace) -> int:
    spec = TaskSpec(
        country_target=args.country,
        hashtag=args.hashtag,
        angle=args.angle,
        hook=args.hook,
        source_post_url=args.source_url,
        x_account_id=args.x_account,
        campaign_id=args.campaign,
        content_id=args.content_id,
        vendor_name=args.vendor,
        deadline=args.deadline or (date.today() + timedelta(days=2)).isoformat(),
        status=args.status or "backlog",
        source="manual",
    )
    try:
        result = create_task(spec, dry_run=args.dry_run, skip_plane=args.local_only)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_from_apify(args: argparse.Namespace) -> int:
    conn = get_connection()
    rows = fetch_high_potential_apify(conn, limit=args.limit)
    conn.close()
    if not rows:
        print(json.dumps({"status": "error", "message": "No high potential apify_posts found"}))
        return 1
    results = []
    for row in rows:
        spec = task_from_apify_row(row)
        if args.ready:
            spec.status = "ready_to_post"
        results.append(create_task(spec, dry_run=args.dry_run, skip_plane=args.local_only))
    print(json.dumps({"status": "success", "tasks": results}, indent=2, ensure_ascii=False))
    return 0


def cmd_from_winning(args: argparse.Namespace) -> int:
    conn = get_connection()
    row = fetch_winning_content(conn, args.content_id)
    conn.close()
    if not row:
        print(json.dumps({"status": "error", "message": "Winning content not found"}))
        return 1
    spec = TaskSpec(
        country_target=row.get("country_target") or "unknown",
        hashtag=row.get("hashtag") or "#xauusd",
        angle=row.get("angle") or "repurpose",
        hook=row.get("hook"),
        source_post_url=row.get("post_url") or row.get("source_post_url"),
        x_account_id=row.get("x_account_id"),
        campaign_id=row.get("campaign_id"),
        content_id=f"{args.content_id}_v2",
        status="ready_to_post",
        source="winning_repurpose",
        raw_payload={"parent_content_id": args.content_id, "join_rate": str(row.get("join_rate"))},
    )
    result = create_task(spec, dry_run=args.dry_run, skip_plane=args.local_only)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_sync_status(vendor_task_id: str, dry_run: bool) -> int:
    try:
        conn = get_connection()
        result = sync_vendor_task_status(conn, vendor_task_id, dry_run=dry_run)
        conn.close()
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1


def cmd_test() -> int:
    """Phase 6 acceptance — local vendor_tasks (+ optional Plane dry-run)."""
    spec = TaskSpec(
        country_target="UAE",
        hashtag="#xauusd",
        angle="breakout",
        hook="Gold breakout above 2350 — repost test",
        source_post_url="https://x.com/hermes_gold_uae/status/demo",
        x_account_id="xacc_uae_001",
        campaign_id="goldhook_20260624",
        content_id="plane_test_001",
        deadline=(date.today() + timedelta(days=1)).isoformat(),
        source="phase6_test",
    )
    plane_dry = create_plane_work_item(spec, dry_run=True)
    result = create_task(spec, dry_run=False, skip_plane=True)
    result["plane_dry_run"] = plane_dry
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Plane vendor/content tasks")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("list-states")
    sub.add_parser("test", help="Phase 6 acceptance (local vendor_tasks)")

    create = sub.add_parser("create", help="Create task from manual spec")
    create.add_argument("--country", required=True)
    create.add_argument("--hashtag", default="#xauusd")
    create.add_argument("--angle", required=True)
    create.add_argument("--hook")
    create.add_argument("--source-url")
    create.add_argument("--x-account")
    create.add_argument("--campaign")
    create.add_argument("--content-id")
    create.add_argument("--vendor")
    create.add_argument("--deadline")
    create.add_argument("--status", default="backlog")
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--local-only", action="store_true", help="Skip Plane API, only vendor_tasks")

    apify = sub.add_parser("from-apify", help="Create from high potential Apify posts")
    apify.add_argument("--limit", type=int, default=1)
    apify.add_argument("--ready", action="store_true", help="Set status ready_to_post")
    apify.add_argument("--dry-run", action="store_true")
    apify.add_argument("--local-only", action="store_true")

    winning = sub.add_parser("from-winning", help="Repurpose winning content")
    winning.add_argument("--content-id", required=True)
    winning.add_argument("--dry-run", action="store_true")
    winning.add_argument("--local-only", action="store_true")

    sync = sub.add_parser("sync-status", help="Sync Plane state → vendor_tasks.status")
    sync.add_argument("--vendor-task-id", required=True)
    sync.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.command == "health":
        return cmd_health()
    if args.command == "list-states":
        return cmd_list_states()
    if args.command == "test":
        return cmd_test()
    if args.command == "create":
        return cmd_create(args)
    if args.command == "from-apify":
        return cmd_from_apify(args)
    if args.command == "from-winning":
        return cmd_from_winning(args)
    if args.command == "sync-status":
        return cmd_sync_status(args.vendor_task_id, args.dry_run)

    return 1


if __name__ == "__main__":
    sys.exit(main())

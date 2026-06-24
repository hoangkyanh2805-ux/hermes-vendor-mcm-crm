#!/usr/bin/env python3
"""
MCM Vendor — Hermes XAUUSD Growth OS v2
Phase 4: Run Apify XAUUSD crawl (Actor EvFXOhwR6wsOWmdSK).

Usage:
    python scripts/run_apify_crawl.py health
    python scripts/run_apify_crawl.py test-canada          # sample normalize pipeline
    python scripts/run_apify_crawl.py run --country Canada --hashtag "#xauusd"
    python scripts/run_apify_crawl.py run --query "#xauusd Canada" --max-items 50
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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "apify-xauusd-crawl.json"
SCRIPTS = Path(__file__).resolve().parent

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_X_ACTOR_ID = os.getenv("APIFY_X_ACTOR_ID", "EvFXOhwR6wsOWmdSK")
APIFY_CRAWL_MAX_ITEMS = int(os.getenv("APIFY_CRAWL_MAX_ITEMS", "500"))
APIFY_CRAWL_DAYS = int(os.getenv("APIFY_CRAWL_DAYS", "30"))


def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def apify_request(method: str, path: str, body: Optional[dict[str, Any]] = None) -> Any:
    if not APIFY_API_TOKEN:
        raise RuntimeError("APIFY_API_TOKEN is not set")
    url = f"https://api.apify.com/v2{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}token={urllib.parse.quote(APIFY_API_TOKEN)}"
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Apify API {exc.code}: {detail}") from exc


def start_actor_run(actor_input: dict[str, Any]) -> str:
    actor_id = APIFY_X_ACTOR_ID.replace("/", "~")
    resp = apify_request("POST", f"/acts/{actor_id}/runs", {"input": actor_input})
    run_id = resp.get("data", {}).get("id")
    if not run_id:
        raise RuntimeError(f"No run id in response: {resp}")
    return run_id


def wait_for_run(run_id: str, timeout_sec: int = 600) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        resp = apify_request("GET", f"/actor-runs/{run_id}")
        data = resp.get("data", {})
        status = data.get("status")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return data
        time.sleep(10)
    raise TimeoutError(f"Apify run {run_id} did not finish in {timeout_sec}s")


def fetch_dataset_items(run_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    resp = apify_request("GET", f"/actor-runs/{run_id}/dataset/items?limit={limit}")
    if isinstance(resp, list):
        return resp
    return resp.get("data", {}).get("items", resp) if isinstance(resp, dict) else []


def build_actor_input(
    *,
    queries: list[str],
    max_items: int,
    last_days: int,
) -> dict[str, Any]:
    """Generic input — adjust keys if your Actor schema differs."""
    return {
        "searchTerms": queries,
        "maxItems": max_items,
        "maxTweets": max_items,
        "query": queries[0] if queries else "#xauusd",
        "queries": queries,
        "sinceDays": last_days,
        "addUserInfo": True,
        "tweetLanguage": "en",
    }


def run_normalize(items: list[dict[str, Any]], crawl_run_id: str, country: str, dry_run: bool) -> dict[str, Any]:
    sys.path.insert(0, str(SCRIPTS))
    from normalize_apify_dataset import process_dataset

    return process_dataset(items, crawl_run_id=crawl_run_id, country=country, persist=not dry_run)


def cmd_health() -> int:
    config = load_config()
    out: dict[str, Any] = {
        "status": "ok",
        "actor_id": APIFY_X_ACTOR_ID,
        "token_set": bool(APIFY_API_TOKEN),
        "countries": len(config.get("countries", [])),
        "queries": len(config.get("queries", [])),
    }
    if APIFY_API_TOKEN:
        try:
            apify_request("GET", f"/acts/{APIFY_X_ACTOR_ID.replace('/', '~')}")
            out["apify_actor"] = "reachable"
        except Exception as exc:
            out["apify_actor"] = f"error: {exc}"
    print(json.dumps(out, indent=2))
    return 0


def cmd_test_canada(dry_run: bool, send_report: bool) -> int:
    """Acceptance path: Canada + #xauusd sample without live Apify."""
    sys.path.insert(0, str(SCRIPTS))
    from normalize_apify_dataset import sample_posts_canada, process_dataset

    crawl_run_id = f"test_canada_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
    items = sample_posts_canada()
    result = process_dataset(items, crawl_run_id=crawl_run_id, country="Canada", persist=not dry_run)

    if send_report and not dry_run:
        from send_telegram_report import send_country_opportunity_report
        try:
            send_country_opportunity_report(result.get("country_intelligence", {}))
            result["telegram_sent"] = True
        except Exception as exc:
            result["telegram_sent"] = False
            result["telegram_error"] = str(exc)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    hooks = result.get("hooks_extracted", 0)
    if not dry_run and hooks < 5:
        print(json.dumps({"warning": f"Only {hooks} hooks extracted, expected >= 5"}))
    return 0


def cmd_run(
    country: Optional[str],
    hashtag: Optional[str],
    query: Optional[str],
    max_items: int,
    dry_run: bool,
    send_report: bool,
) -> int:
    config = load_config()
    if query:
        queries = [query]
    elif country and hashtag:
        queries = [f"{hashtag} {country}"]
    else:
        queries = config.get("queries", [])[:4]

    crawl_run_id = f"apify_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    if not APIFY_API_TOKEN:
        print(json.dumps({
            "status": "error",
            "message": "APIFY_API_TOKEN not set — use test-canada for offline acceptance",
        }))
        return 1

    actor_input = build_actor_input(
        queries=queries,
        max_items=min(max_items, APIFY_CRAWL_MAX_ITEMS),
        last_days=APIFY_CRAWL_DAYS,
    )
    run_id = start_actor_run(actor_input)
    run_data = wait_for_run(run_id)
    if run_data.get("status") != "SUCCEEDED":
        raise RuntimeError(f"Apify run failed: {run_data.get('status')}")

    items = fetch_dataset_items(run_id, limit=max_items)
    if not items:
        raise RuntimeError("Apify returned empty dataset")

    country_target = country or "Canada"
    result = run_normalize(items, f"{crawl_run_id}_{run_id}", country_target, dry_run)

    if send_report and not dry_run:
        sys.path.insert(0, str(SCRIPTS))
        from send_telegram_report import send_country_opportunity_report
        try:
            send_country_opportunity_report(result.get("country_intelligence", {}))
            result["telegram_sent"] = True
        except Exception as exc:
            result["telegram_sent"] = False
            result["telegram_error"] = str(exc)

    result["apify_run_id"] = run_id
    result["queries"] = queries
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Apify XAUUSD country crawl")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Check Apify config and token")

    test = sub.add_parser("test-canada", help="Sample Canada #xauusd pipeline (no Apify)")
    test.add_argument("--dry-run", action="store_true")
    test.add_argument("--report", action="store_true", help="Send Telegram admin report")

    run = sub.add_parser("run", help="Live Apify crawl")
    run.add_argument("--country")
    run.add_argument("--hashtag", default="#xauusd")
    run.add_argument("--query")
    run.add_argument("--max-items", type=int, default=50)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--report", action="store_true")

    args = parser.parse_args()

    try:
        if args.command == "health":
            return cmd_health()
        if args.command == "test-canada":
            return cmd_test_canada(args.dry_run, args.report)
        if args.command == "run":
            return cmd_run(
                args.country, args.hashtag, args.query, args.max_items,
                args.dry_run, args.report,
            )
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())

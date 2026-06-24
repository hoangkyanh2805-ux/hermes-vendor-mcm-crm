#!/usr/bin/env python3
"""
MCM Vendor — Hermes XAUUSD Growth OS v2
Phase 4: Normalize Apify dataset → apify_posts + country_intelligence.

Usage:
    python scripts/normalize_apify_dataset.py --sample
    python scripts/normalize_apify_dataset.py --file data/apify_raw.json --crawl-run-id run_123
    python scripts/normalize_apify_dataset.py --sample --country Canada --report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import Counter
from datetime import date, datetime, timezone
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
CONFIG_PATH = ROOT / "config" / "apify-xauusd-crawl.json"
PROMPT_CLASSIFY = ROOT / "prompts" / "apify-classify-post.txt"
PROMPT_HOOK = ROOT / "prompts" / "apify-hook-extract.txt"

DATABASE_URL = os.getenv("DATABASE_URL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SIGNAL_WORDS = {"signal", "buy", "sell", "entry", "tp", "sl", "setup", "long", "short", "xauusd"}
PROOF_WORDS = {"profit", "pips", "win", "gain", "result", "closed", "+%", "screenshot"}
EDU_WORDS = {"learn", "tutorial", "how to", "guide", "analysis", "explained", "strategy"}
PROMO_WORDS = {"vip", "join", "dm me", "link in bio", "telegram", "subscribe", "discount", "free group"}


def json_safe(obj: Any) -> Any:
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL)


def log_activity(conn, **kwargs) -> None:
    kwargs.setdefault("actor", "normalize_apify")
    kwargs.setdefault("source", "apify")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO activity_logs (entity_type, entity_id, action, status, message, actor, source, error_detail, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                kwargs.get("entity_type", "apify_posts"),
                kwargs.get("entity_id"),
                kwargs.get("action", "normalize"),
                kwargs.get("status", "success"),
                kwargs.get("message"),
                kwargs["actor"],
                kwargs["source"],
                kwargs.get("error_detail"),
                json.dumps(kwargs.get("payload") or {}),
            ),
        )
    conn.commit()


def log_system_health(conn, status: str, message: str, details: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO system_health_logs (service_name, status, message, details)
            VALUES ('apify_crawl', %s, %s, %s)
            """,
            (status, message, json.dumps(details)),
        )
    conn.commit()


def sample_posts_canada() -> list[dict[str, Any]]:
    """20+ sample posts for acceptance test without live Apify."""
    base = [
        ("Gold breakout above 2350 — XAUUSD long setup with tight SL", "signal", "High", "breakout long"),
        ("+$420 on gold today. Same system every week.", "proof", "High", "profit proof"),
        ("How I read XAUUSD on the 4H — beginner thread", "education", "Medium", "4H tutorial"),
        ("Join VIP gold signals — link in bio", "promo", "Low", "vip promo"),
        ("Random crypto moon post not about gold", "noise", "Low", ""),
        ("Fed week gold volatility playbook #xauusd", "education", "Medium", "fed volatility"),
        ("Selling XAUUSD at resistance 2365, TP 2340", "signal", "High", "resistance short"),
        ("3 wins 0 losses this week on gold scalps", "proof", "High", "scalp wins"),
        ("What is spread on XAUUSD for Canadian traders?", "education", "Medium", "canada basics"),
        ("FREE GOLD BOT 1000% gain click here", "noise", "Low", ""),
        ("London open gold liquidity grab — watch 2348", "signal", "High", "london open"),
        ("My gold journal: discipline beats prediction", "education", "Medium", "trading journal"),
        ("UAE session XAUUSD range trade idea", "signal", "Medium", "session range"),
        ("Another generic motivational quote", "noise", "Low", ""),
        ("Gold dips on USD strength — quick recap", "education", "Medium", "usd correlation"),
        ("VIP channel closing soon DM now", "promo", "Low", "urgency promo"),
        ("Closed +80 pips XAUUSD from Asia low", "proof", "High", "asia session win"),
        ("Weekly gold levels every Sunday — save this", "education", "Medium", "weekly levels"),
        ("XAUUSD triangle breakout incoming?", "signal", "Medium", "triangle setup"),
        ("Spam giveaway not trading related", "noise", "Low", ""),
        ("Canada traders: tax tips on gold profits", "education", "Low", "off-topic edu"),
        ("Precision entry 2351.2 gold — risk 0.5%", "signal", "High", "precision entry"),
    ]
    items = []
    for i, (text, cat_hint, potential, angle) in enumerate(base):
        likes = 50 + (i * 17) % 500
        items.append({
            "id": f"sample_{i}",
            "url": f"https://x.com/goldtrader{i}/status/100000000000{i}",
            "text": text,
            "fullText": text,
            "searchQuery": "#xauusd Canada",
            "author": {"userName": f"goldtrader{i}", "name": f"Gold Trader {i}", "followers": 1000 + i * 200},
            "likeCount": likes,
            "replyCount": i % 30,
            "retweetCount": i % 20,
            "viewCount": likes * 10,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "_sample_category": cat_hint,
            "_sample_potential": potential,
            "_sample_angle": angle,
        })
    return items


def extract_hashtag(text: str, query: str) -> Optional[str]:
    for tag in ("#xauusd", "#gold", "#XAUUSD", "#Gold"):
        if tag.lower() in (text + " " + query).lower():
            return tag.lower() if tag.startswith("#") else tag
    m = re.search(r"#\w+", text or "")
    return m.group(0).lower() if m else None


def infer_country(query: str, default: str = "unknown") -> str:
    config = load_config()
    q = (query or "").lower()
    for country in config.get("countries", []):
        if country.lower() in q:
            return country
    aliases = {"uae": "United Arab Emirates", "ksa": "Saudi Arabia", "uk": "United Kingdom"}
    for alias, full in aliases.items():
        if alias in q:
            return full
    return default


def engagement_score(likes: int, replies: int, reposts: int, views: int) -> float:
    return round(likes * 1.0 + replies * 2.0 + reposts * 1.5 + views * 0.001, 2)


def classify_rule_based(text: str, likes: int, followers: int) -> dict[str, str]:
    t = (text or "").lower()
    category = "noise"
    if any(w in t for w in PROMO_WORDS):
        category = "promo"
    if any(w in t for w in EDU_WORDS):
        category = "education"
    if any(w in t for w in PROOF_WORDS):
        category = "proof"
    if any(w in t for w in SIGNAL_WORDS):
        category = "signal"

    potential = "Low"
    if category in ("signal", "proof") and (likes > 30 or followers > 2000):
        potential = "High"
    elif category == "education" and likes > 20:
        potential = "Medium"
    elif category == "signal":
        potential = "Medium"

    action = "skip"
    if potential == "High":
        action = "rewrite" if category in ("signal", "proof") else "comment"
    elif potential == "Medium":
        action = "seed"

    angle = "general gold"
    if "breakout" in t:
        angle = "breakout setup"
    elif "fed" in t or "nfp" in t:
        angle = "macro catalyst"
    elif "scalp" in t:
        angle = "scalp session"
    elif "vip" in t or "join" in t:
        angle = "community promo"

    return {
        "category": category,
        "lead_potential": potential,
        "content_angle": angle,
        "action": action,
    }


def extract_hook_rule_based(text: str, category: str) -> str:
    if category in ("noise", "promo"):
        return ""
    t = (text or "").strip()
    if len(t) <= 120:
        return t
    first = re.split(r"[.!?\n]", t)[0].strip()
    return first[:160] if first else t[:120]


def normalize_item(raw: dict[str, Any], crawl_run_id: str, country_override: Optional[str] = None) -> dict[str, Any]:
    text = raw.get("text") or raw.get("fullText") or raw.get("post_text") or ""
    query = raw.get("searchQuery") or raw.get("query") or ""
    author = raw.get("author") or {}
    handle = author.get("userName") or author.get("handle") or raw.get("author_handle")
    name = author.get("name") or raw.get("author_name")
    followers = int(author.get("followers") or raw.get("author_followers") or 0)
    likes = int(raw.get("likeCount") or raw.get("likes") or 0)
    replies = int(raw.get("replyCount") or raw.get("replies") or 0)
    reposts = int(raw.get("retweetCount") or raw.get("reposts") or 0)
    views = int(raw.get("viewCount") or raw.get("views") or 0)
    country = country_override or infer_country(query, infer_country(text, "unknown"))

    if raw.get("_sample_category"):
        classified = {
            "category": raw["_sample_category"],
            "lead_potential": raw["_sample_potential"],
            "content_angle": raw.get("_sample_angle", "gold"),
            "action": "rewrite" if raw["_sample_potential"] == "High" else "seed",
        }
    else:
        classified = classify_rule_based(text, likes, followers)

    hook = extract_hook_rule_based(text, classified["category"])

    return {
        "platform": "x",
        "query": query,
        "country_target": country,
        "hashtag": extract_hashtag(text, query),
        "post_url": raw.get("url") or raw.get("post_url"),
        "post_text": text,
        "author_handle": handle,
        "author_name": name,
        "author_followers": followers,
        "created_at_post": raw.get("createdAt") or raw.get("created_at"),
        "likes": likes,
        "replies": replies,
        "reposts": reposts,
        "views": views,
        "engagement_score": engagement_score(likes, replies, reposts, views),
        "category": classified["category"],
        "lead_potential": classified["lead_potential"],
        "hook_extracted": hook,
        "content_angle": classified["content_angle"],
        "action": classified["action"],
        "crawl_run_id": crawl_run_id,
        "raw_json": raw,
    }


def insert_posts(conn, posts: list[dict[str, Any]]) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for p in posts:
            cur.execute(
                """
                INSERT INTO apify_posts (
                    platform, query, country_target, hashtag, post_url, post_text,
                    author_handle, author_name, author_followers, created_at_post,
                    likes, replies, reposts, views, engagement_score,
                    category, lead_potential, hook_extracted, content_angle, action,
                    crawl_run_id, raw_json
                ) VALUES (
                    %(platform)s, %(query)s, %(country_target)s, %(hashtag)s, %(post_url)s, %(post_text)s,
                    %(author_handle)s, %(author_name)s, %(author_followers)s, %(created_at_post)s,
                    %(likes)s, %(replies)s, %(reposts)s, %(views)s, %(engagement_score)s,
                    %(category)s, %(lead_potential)s, %(hook_extracted)s, %(content_angle)s, %(action)s,
                    %(crawl_run_id)s, %(raw_json)s
                )
                """,
                {**p, "raw_json": json.dumps(p["raw_json"])},
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted


def build_country_intelligence(posts: list[dict[str, Any]], report_date: date, country: str) -> dict[str, Any]:
    country_posts = [p for p in posts if p.get("country_target") == country]
    if not country_posts:
        country_posts = posts

    hashtags = Counter(p.get("hashtag") or "none" for p in country_posts)
    hooks = [p["hook_extracted"] for p in country_posts if p.get("hook_extracted")]
    authors = Counter(p.get("author_handle") or "unknown" for p in country_posts)
    angles = Counter(p.get("content_angle") or "general" for p in country_posts)
    high = [p for p in country_posts if p.get("lead_potential") == "High"]
    noise_count = sum(1 for p in country_posts if p.get("category") == "noise")

    rewrite = [
        {"post_url": p["post_url"], "hook": p.get("hook_extracted"), "score": p.get("engagement_score")}
        for p in high if p.get("action") == "rewrite"
    ][:5]
    seed = [
        {"post_url": p["post_url"], "author": p.get("author_handle"), "action": "comment"}
        for p in country_posts if p.get("action") in ("comment", "seed") and p.get("lead_potential") != "Low"
    ][:5]

    vendor_tasks = [
        f"[{country}] Rewrite hook: {(rewrite[0].get('hook') or '')[:80]}" if rewrite else f"[{country}] Research new #xauusd angle",
        f"[{country}] Seed comment on @{seed[0]['author']}" if seed else f"[{country}] Schedule #gold education post",
        f"[{country}] Review {len(high)} high-potential posts for Plane tasks",
    ]

    noise_warning = None
    if noise_count > len(country_posts) * 0.4:
        noise_warning = f"High noise ratio: {noise_count}/{len(country_posts)} posts flagged spam/off-topic"

    return {
        "report_date": report_date,
        "country_target": country,
        "top_hashtag": hashtags.most_common(1)[0][0] if hashtags else None,
        "top_hook": hooks[0] if hooks else None,
        "top_author": authors.most_common(1)[0][0] if authors else None,
        "top_content_angle": angles.most_common(1)[0][0] if angles else None,
        "posts_crawled": len(country_posts),
        "high_potential_count": len(high),
        "noise_warning": noise_warning,
        "vendor_task_suggestions": vendor_tasks,
        "posts_to_rewrite": rewrite,
        "posts_to_seed": seed,
        "raw_payload": {"crawl_run_id": country_posts[0].get("crawl_run_id") if country_posts else None},
    }


def upsert_country_intelligence(conn, intel: dict[str, Any]) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO country_intelligence (
                report_date, country_target, top_hashtag, top_hook, top_author, top_content_angle,
                posts_crawled, high_potential_count, noise_warning,
                vendor_task_suggestions, posts_to_rewrite, posts_to_seed, raw_payload
            ) VALUES (
                %(report_date)s, %(country_target)s, %(top_hashtag)s, %(top_hook)s, %(top_author)s,
                %(top_content_angle)s, %(posts_crawled)s, %(high_potential_count)s, %(noise_warning)s,
                %(vendor_task_suggestions)s, %(posts_to_rewrite)s, %(posts_to_seed)s, %(raw_payload)s
            )
            ON CONFLICT (report_date, country_target) DO UPDATE SET
                top_hashtag = EXCLUDED.top_hashtag,
                top_hook = EXCLUDED.top_hook,
                top_author = EXCLUDED.top_author,
                top_content_angle = EXCLUDED.top_content_angle,
                posts_crawled = EXCLUDED.posts_crawled,
                high_potential_count = EXCLUDED.high_potential_count,
                noise_warning = EXCLUDED.noise_warning,
                vendor_task_suggestions = EXCLUDED.vendor_task_suggestions,
                posts_to_rewrite = EXCLUDED.posts_to_rewrite,
                posts_to_seed = EXCLUDED.posts_to_seed,
                raw_payload = EXCLUDED.raw_payload,
                updated_at = NOW()
            RETURNING id
            """,
            {
                **intel,
                "vendor_task_suggestions": json.dumps(intel["vendor_task_suggestions"]),
                "posts_to_rewrite": json.dumps(intel["posts_to_rewrite"]),
                "posts_to_seed": json.dumps(intel["posts_to_seed"]),
                "raw_payload": json.dumps(intel["raw_payload"]),
            },
        )
        row = cur.fetchone()
    conn.commit()
    return str(row[0])


def process_dataset(
    items: list[dict[str, Any]],
    *,
    crawl_run_id: Optional[str] = None,
    country: Optional[str] = None,
    persist: bool = True,
) -> dict[str, Any]:
    crawl_run_id = crawl_run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    normalized = [normalize_item(item, crawl_run_id, country_override=country) for item in items]
    hooks = [p for p in normalized if p.get("hook_extracted")]
    report_date = date.today()

    result = {
        "crawl_run_id": crawl_run_id,
        "posts_normalized": len(normalized),
        "hooks_extracted": len(hooks),
        "high_potential": sum(1 for p in normalized if p.get("lead_potential") == "High"),
        "by_category": dict(Counter(p["category"] for p in normalized)),
    }

    if not persist:
        intel = build_country_intelligence(normalized, report_date, country or "Canada")
        result["country_intelligence"] = intel
        result["sample_posts"] = normalized[:3]
        return result

    conn = get_connection()
    try:
        inserted = insert_posts(conn, normalized)
        intel = build_country_intelligence(normalized, report_date, country or normalized[0].get("country_target", "Canada"))
        intel_id = upsert_country_intelligence(conn, intel)
        log_activity(
            conn,
            entity_type="apify_posts",
            entity_id=crawl_run_id,
            action="normalize_complete",
            message=f"Normalized {len(normalized)} posts, inserted {inserted}",
            payload=result,
        )
        log_system_health(
            conn,
            "healthy",
            f"Apify normalize OK: {len(normalized)} posts",
            {**result, "country_intelligence_id": intel_id},
        )
        result["inserted"] = inserted
        result["country_intelligence_id"] = intel_id
        result["country_intelligence"] = intel
    except Exception as exc:
        log_activity(
            conn,
            entity_type="apify_posts",
            entity_id=crawl_run_id,
            action="normalize_complete",
            status="failure",
            message="Normalize failed",
            error_detail=str(exc),
        )
        log_system_health(conn, "down", str(exc), {"crawl_run_id": crawl_run_id})
        raise
    finally:
        conn.close()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize Apify dataset to Supabase")
    parser.add_argument("--file", help="Raw JSON array from Apify dataset")
    parser.add_argument("--sample", action="store_true", help="Use 22 sample Canada #xauusd posts")
    parser.add_argument("--country", default="Canada")
    parser.add_argument("--crawl-run-id")
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--report", action="store_true", help="Print country intel JSON")
    args = parser.parse_args()

    if args.sample:
        items = sample_posts_canada()
    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            items = json.load(f)
    else:
        print(json.dumps({"error": "Use --sample or --file"}))
        return 1

    result = process_dataset(
        items,
        crawl_run_id=args.crawl_run_id,
        country=args.country,
        persist=not args.dry_run,
    )
    if args.report:
        print(json.dumps(result.get("country_intelligence", result), indent=2, ensure_ascii=False, default=json_safe))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=json_safe))
    return 0


if __name__ == "__main__":
    sys.exit(main())

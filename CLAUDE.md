# CLAUDE.md — MCM Vendor Hermes XAUUSD Growth OS v2

Project context for AI assistants (Claude, Cursor, Hermes).  
Lifecycle: **DEFINE → PLAN → BUILD → VERIFY → REVIEW → SHIP** per [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills).

---

## Non-negotiable rules

1. **1 Hermes instance = exactly 5 skill files** — no Agent 6, no five separate Hermes deployments.
2. **Supabase/Postgres is the source of truth** — no Google Sheet write path.
3. **Twenty CRM** for pipeline (EspoCRM = legacy reference only, `agent4-crm-sync.yaml`).
4. **Activepieces** for automation MVP — do not add n8n unless ADR is opened.
5. **Agent 5** updates bundle after every phase SHIP: `bundle-manifest.md`, `sop-ops.md`, `runbook.md`, `launch-checklist.md`, `rollback-plan.md`.
6. All automations log to **`activity_logs`** on failure.

---

## Five skills

| # | File | Role |
| - | ---- | ---- |
| 1 | `skills/agent1-capture.yaml` | Telegram /start, deep link attribution |
| 2 | `skills/agent2-onboard.yaml` | D1–D7 nurture (MVP: documented + manual) |
| 3 | `skills/agent3-daily-loop.yaml` | Apify crawl, classify, country reports |
| 4 | `skills/agent4-twenty-crm-sync.yaml` | Supabase → Twenty sync |
| 5 | `skills/agent5-monitor.yaml` | Health, 8PM founder report, weekly review, bundle |

---

## Architecture

```
X → BioLink/UTM → Telegram → Supabase
  → Twenty → Metabase → Plane → Activepieces → Agent 5 rhythm
```

ADRs: `docs/adr/001` through `005`.

---

## Deep link format

```
src_{x_account}_{country}_{campaign}[_{content_id}]
```

Parser: `scripts/sync_to_supabase.py` — country token from rightmost known country list.

---

## Key scripts

| Script | Use |
| ------ | --- |
| `scripts/sync_to_supabase.py` | Health, capture, content tracker |
| `scripts/sync_to_twenty.py` | CRM sync |
| `scripts/send_telegram_report.py` | Welcome, admin, founder-daily |
| `scripts/run_apify_crawl.py` | Apify actor |
| `scripts/normalize_apify_dataset.py` | Classify + country intel |
| `scripts/create_plane_task.py` | Vendor/content tasks |
| `scripts/activepieces_webhook_test.py` | Flow webhooks + failure logs |
| `scripts/health_check.py` | Stack health, founder-data, bundle verify |
| `scripts/e2e_launch_test.py` | Phase 9 E2E launch test |

---

## Database

Deploy order: `db/schema.sql` → `db/seed_stages.sql` → `db/views.sql`

Key tables: `leads`, `telegram_joins`, `crm_stage_events`, `content_performance`, `vendor_tasks`, `activity_logs`, `system_health_logs`.

---

## When implementing changes

- Read surrounding code and match existing patterns.
- Minimize scope — one phase, one concern.
- Update Agent 5 docs if shipping a phase.
- Run relevant acceptance: `content-test`, `e2e_launch_test.py`, `health_check.py bundle`.
- Commit convention: `done: phaseN short-description` (only when user asks to commit).

---

## Cron (production)

```
*/30 * * * *  health_check.py --persist
0 20 * * *    send_telegram_report.py founder-daily
0  9 * * 1    send_telegram_report.py founder-daily --weekly
```

Agent 3 Apify cron: see `skills/agent3-daily-loop.yaml`.

---

## Docs index

- Master plan: `docs/master-plan.md`
- SOP: `docs/sop-ops.md`
- Runbook: `docs/runbook.md`
- Launch: `docs/launch-checklist.md`
- Rollback: `docs/rollback-plan.md`
- Bundle: `docs/bundle-manifest.md`
- Case study map: `docs/case-study-mapping.md`
- README: `README.md`

---

## Phase status (v2)

Phases 0–8: code complete. Phase 9: E2E test. Phase 10: SOP bundle complete.

Production go-live items in `launch-checklist.md` (Telegram bot live, Twenty stages, Metabase UI, etc.) are operator tasks beyond repo SHIP.

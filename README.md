# MCM Vendor — Hermes XAUUSD Growth OS v2

Growth Operating System for X → Telegram → CRM → Dashboard → Vendor ops.  
Built on [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) lifecycle: **DEFINE → PLAN → BUILD → VERIFY → REVIEW → SHIP**.

**1 Hermes instance = 5 skills.** Supabase = source of truth. No Google Sheet writes.

---

## Architecture

```
X traffic → BioLink/UTM → Telegram /start → Supabase (SoT)
  → Twenty CRM → Metabase → Plane → Activepieces → Agent 5 rhythm
```

| Layer | Tool | Role |
| ----- | ---- | ---- |
| Capture | Telegram + Agent 1 | Attribution via deep link |
| SoT | Supabase/Postgres | Leads, joins, content, logs |
| CRM | Twenty | Pipeline visibility |
| Dashboard | Metabase | Founder KPIs (15 SQL views) |
| Intelligence | Apify + Agent 3 | Country/hook intel |
| Vendor ops | Plane + Agent 6-less board | Content tasks for team |
| Automation | Activepieces | Webhooks between layers |
| Rhythm | Agent 5 | Health, 8PM report, weekly review |

See ADRs in [`docs/adr/`](docs/adr/).

---

## Quick start

### 1. Prerequisites

- Python 3.11+
- Docker (local Postgres) or Supabase project
- Telegram bot token ([@BotFather](https://t.me/BotFather))
- Optional: Twenty, Metabase, Plane, Activepieces, Apify accounts

### 2. Clone and configure

```bash
git clone <repo-url> hermes-growth-os
cd hermes-growth-os
cp .env.example .env
# Edit .env — minimum: DATABASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID
pip install -r requirements.txt
```

### 3. Database (local)

```bash
docker compose up -d
# DATABASE_URL=postgresql://hermes:hermes_dev@localhost:5432/hermes_growth
```

Production: run `db/schema.sql`, `db/seed_stages.sql`, `db/views.sql` on Supabase.

### 4. Smoke tests

```bash
python scripts/sync_to_supabase.py health
python scripts/sync_to_supabase.py test-join
python scripts/health_check.py
python scripts/e2e_launch_test.py
```

### 5. Hermes skills

Load all five YAML files into one Hermes instance:

| Skill | File |
| ----- | ---- |
| Capture | `skills/agent1-capture.yaml` |
| Onboard | `skills/agent2-onboard.yaml` |
| Daily loop | `skills/agent3-daily-loop.yaml` |
| CRM sync | `skills/agent4-twenty-crm-sync.yaml` |
| Monitor | `skills/agent5-monitor.yaml` |

---

## Key commands

| Task | Command |
| ---- | ------- |
| Capture test | `python scripts/sync_to_supabase.py capture-start --user-id ID --payload "src_..."` |
| Twenty sync | `python scripts/sync_to_twenty.py sync-lead --telegram-user-id ID` |
| Apify test | `python scripts/run_apify_crawl.py test-canada --report` |
| Content tracker | `python scripts/sync_to_supabase.py content-test` |
| Plane task | `python scripts/create_plane_task.py test` |
| Activepieces | `python scripts/activepieces_webhook_test.py test` |
| Founder report | `python scripts/send_telegram_report.py founder-daily --dry-run` |
| E2E launch | `python scripts/e2e_launch_test.py` |
| Bundle verify | `python scripts/health_check.py bundle` |

Full runbook: [`docs/runbook.md`](docs/runbook.md)  
**VPS deploy (webhook + Metabase):** [`docs/deploy-vps-metabase.md`](docs/deploy-vps-metabase.md)

---

## Deep link format

```
https://t.me/YOUR_BOT?start=src_{x_account}_{country}_{campaign}[_{content_id}]
```

Example:

```
https://t.me/hermes7979_bot?start=src_xacc_uae_001_uae_goldhook_20260624_hook001
```

---

## Cron (production VPS)

```cron
*/30 * * * *  python scripts/health_check.py --persist
0  6 * * *    python scripts/run_apify_crawl.py run --country Canada --hashtag "#xauusd"
0 20 * * *    python scripts/send_telegram_report.py founder-daily
0  9 * * 1    python scripts/send_telegram_report.py founder-daily --weekly
```

Adjust per `skills/agent3-daily-loop.yaml` and `skills/agent5-monitor.yaml`.

---

## Documentation map

| Doc | Purpose |
| --- | ------- |
| [`docs/master-plan.md`](docs/master-plan.md) | Phase roadmap 0–10 |
| [`docs/sop-ops.md`](docs/sop-ops.md) | Per-phase SOP |
| [`docs/runbook.md`](docs/runbook.md) | Daily operations |
| [`docs/launch-checklist.md`](docs/launch-checklist.md) | Go-live checklist |
| [`docs/rollback-plan.md`](docs/rollback-plan.md) | Incident rollback |
| [`docs/bundle-manifest.md`](docs/bundle-manifest.md) | SOP package inventory |
| [`docs/case-study-mapping.md`](docs/case-study-mapping.md) | Case study → modules |
| [`CLAUDE.md`](CLAUDE.md) | AI assistant project rules |

---

## Adapting to another vertical

**Change:** landing copy, D1–D7 scripts, countries, hashtags, CRM stage labels, qualification rules.  
**Keep:** 5 skills, Supabase SoT, Twenty + Metabase + Plane + Activepieces pattern, Agent 5 rhythm.

See [`docs/case-study-mapping.md`](docs/case-study-mapping.md).

---

## License / usage

Internal MCM Vendor Growth OS. EspoCRM skill (`agent4-crm-sync.yaml`) is legacy reference only.

# MCM Vendor — Hermes XAUUSD Growth OS v2
# Standard Operating Procedures

Execution framework: [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)  
Lifecycle: **DEFINE → PLAN → BUILD → VERIFY → REVIEW → SHIP**

**Master plan:** [master-plan.md](master-plan.md)  
**Runbook:** [runbook.md](runbook.md) | **Bundle:** [bundle-manifest.md](bundle-manifest.md)

> **Agent 5 rule:** Sau mỗi phase SHIP → cập nhật bundle-manifest, sop-ops, runbook, launch-checklist. Không đợi Phase 10.

---

## Phase 0 — Supabase/Postgres Source of Truth

**Status:** Complete  
**ADR:** [001-source-of-truth-supabase.md](adr/001-source-of-truth-supabase.md)

### 1. SPEC

| Item | Definition |
| ---- | ---------- |
| **Requirement** | Single relational source of truth for leads, joins, stages, content, intelligence, and audit logs |
| **Source of truth** | Supabase/Postgres (`DATABASE_URL`) |
| **Inputs** | Telegram `/start` payloads, future Apify crawls, CRM stage changes, vendor tasks |
| **Outputs** | Normalized rows in 16 core tables + 7 SQL views |
| **Acceptance** | Schema runs; stages seeded; fake join inserts; `activity_logs` records events; no Google Sheet dependency |
| **Failure cases** | Missing `DATABASE_URL`, FK violations, duplicate Telegram user, invalid campaign/X account |

### 2. PLAN

**Affected files:**

```
db/schema.sql
db/seed_stages.sql
db/views.sql
scripts/sync_to_supabase.py
.env.example
docs/sop-ops.md
docs/adr/001-source-of-truth-supabase.md
```

**Atomic steps:**

1. Run `schema.sql` — tables, triggers, `log_activity()` helper
2. Run `seed_stages.sql` — 8 CRM stages + demo vendor/campaign/X account
3. Run `views.sql` — dashboard views for Metabase (Phase 3)
4. Use `sync_to_supabase.py` for lead/join upserts and acceptance tests

**Dependencies:** Supabase project or local Postgres 14+

**Not built yet:** Twenty sync (Phase 2), Metabase cards (Phase 3)

### 3. BUILD

#### Deploy schema

```bash
# Supabase SQL editor, or local:
psql "$DATABASE_URL" -f db/schema.sql
psql "$DATABASE_URL" -f db/seed_stages.sql
psql "$DATABASE_URL" -f db/views.sql
```

#### Core tables

| Table | Purpose |
| ----- | ------- |
| `crm_stages` | Pipeline stage reference |
| `x_accounts` | X/Twitter account registry |
| `vendors` | Vendor/affiliate operators |
| `campaigns` | UTM/campaign attribution |
| `telegram_joins` | Raw join capture events |
| `leads` | Primary attribution entity |
| `members` | Qualified community members |
| `affiliate_profiles` | Affiliate tier tracking |
| `content_assets` | Content library |
| `content_performance` | Post metrics + join attribution |
| `apify_posts` | Normalized crawl output |
| `country_intelligence` | Daily country reports |
| `vendor_tasks` | Plane task mirror |
| `crm_stage_events` | Stage transition audit |
| `activity_logs` | System-wide audit trail |
| `daily_kpis` | Founder report rollup |
| `system_health_logs` | Service health checks |

#### CRM stages (seeded)

1. New X Visitor  
2. Telegram Joined  
3. Warm Member  
4. Signal Interested  
5. Trial / Consult  
6. Paid / VIP  
7. Renewal Risk  
8. Churned  

#### Views

- `v_daily_growth`
- `v_country_performance`
- `v_vendor_performance`
- `v_content_performance`
- `v_crm_stage_funnel`
- `v_purgatory_dashboard`
- `v_system_health`

#### Python sync utility

```bash
pip install -r requirements.txt
cp .env.example .env   # set DATABASE_URL

python scripts/sync_to_supabase.py health
python scripts/sync_to_supabase.py test-join
python scripts/sync_to_supabase.py test-join --payload "src_xacc_uae_001_uae_goldhook_20260624"
python scripts/sync_to_supabase.py test-join --payload ""
```

### 4. TEST

#### Health check

```bash
python scripts/sync_to_supabase.py health
```

Expected: `status: healthy`, `crm_stages: 8`

#### Valid payload join

```bash
python scripts/sync_to_supabase.py test-join --payload "src_xacc_uae_001_uae_goldhook_20260624"
```

Sample result:

```json
{
  "status": "success",
  "result": {
    "telegram_join_id": "<uuid>",
    "lead_id": "<uuid>",
    "is_duplicate": false,
    "parse_status": "ok",
    "source_account": "xacc_uae_001",
    "country_target": "uae",
    "campaign_id": "goldhook_20260624"
  }
}
```

#### Verify DB

```sql
SELECT * FROM telegram_joins ORDER BY created_at DESC LIMIT 1;
SELECT * FROM leads WHERE telegram_user_id = 999000001;
SELECT * FROM activity_logs WHERE entity_type IN ('leads', 'telegram_joins') ORDER BY created_at DESC LIMIT 5;
```

#### Missing payload (unknown source)

```bash
python scripts/sync_to_supabase.py test-join --payload ""
```

Expected: `parse_status: missing_payload`, stage `New X Visitor`

#### Duplicate join

Run `test-join` twice with same `TEST_TELEGRAM_USER_ID`. Second run: `is_duplicate: true`, no duplicate lead row.

#### Failure path

Unset `DATABASE_URL` and run `test-join`. Expected: error JSON + `activity_logs` row with `status: failure` (if DB reconnects).

### 5. REVIEW

| Check | Status |
| ----- | ------ |
| Correctness — all 16 tables + 7 views | ✓ |
| Readability — schema commented by section | ✓ |
| Architecture — Supabase SoT, no Sheet write path | ✓ |
| Security — `.env` gitignored, no secrets in repo | ✓ |
| Performance — indexes on join_time, stage, country | ✓ |

### 6. SHIP

**Launch checklist (Phase 0):**

- [ ] `DATABASE_URL` set in production `.env`
- [ ] `schema.sql` + `seed_stages.sql` + `views.sql` deployed
- [ ] `sync_to_supabase.py health` returns healthy
- [ ] Test join creates `telegram_joins` + `leads` + `activity_logs`
- [ ] Google Sheet not required for any write path

**Suggested commit:**

```bash
git commit -m "done: phase0 supabase-source-of-truth-schema"
```

---

## Phase 1 — Telegram / BioLink / UTM Attribution

**Status:** Complete  
**Depends on:** Phase 0  
**Skill:** `skills/agent1-capture.yaml`

### 1. SPEC

| Item | Definition |
| ---- | ---------- |
| **Requirement** | Track exactly where every Telegram join came from via deep-link `/start` payload |
| **Source of truth** | Supabase (`telegram_joins`, `leads`) — unchanged from Phase 0 |
| **Flow** | X post → BioLink/UTM → `t.me/bot?start=src_...` → Agent 1 → Supabase → welcome + admin |
| **Inputs** | `telegram_user_id`, `telegram_username`, `/start` payload |
| **Outputs** | Upserted join/lead rows, welcome DM, admin summary, `activity_logs` |
| **Acceptance** | Valid payload attributed; missing payload → unknown; duplicate updates; admin notified |
| **Failure cases** | Missing payload, duplicate user, invalid campaign, unknown X account/country, DB error, Telegram send failure |

#### Deep link format

```
https://t.me/hermes7979_bot?start=src_{x_account_id}_{country}_{campaign_id}[_{content_id}]
```

Example:

```
https://t.me/hermes7979_bot?start=src_xacc_uae_001_uae_goldhook_20260624
```

### 2. PLAN

**Affected files:**

```
skills/agent1-capture.yaml
scripts/sync_to_supabase.py
scripts/send_telegram_report.py
db/schema.sql          # parse_status + unknown_country
docs/sop-ops.md
```

**Atomic steps:**

1. Parse `/start` payload → `source_account`, `country`, `campaign`, `content`
2. Validate references against `x_accounts`, `campaigns`, known countries
3. Upsert `telegram_joins` + `leads`, set stage
4. Send welcome message to user
5. Send admin source summary
6. Log all failures to `activity_logs` (DB writes are not rolled back on Telegram failure)

**Not built yet:** Twenty sync on join (Phase 2), Activepieces webhook (Phase 7)

### 3. BUILD

#### Agent 1 capture (full flow)

```bash
python scripts/sync_to_supabase.py capture-start \
  --user-id 123456789 \
  --username alice \
  --payload "src_xacc_uae_001_uae_goldhook_20260624"
```

DB-only test (no Telegram):

```bash
python scripts/sync_to_supabase.py capture-start \
  --user-id 123456789 --username alice \
  --payload "src_xacc_uae_001_uae_goldhook_20260624" \
  --no-welcome --no-admin
```

#### Telegram scripts

```bash
python scripts/send_telegram_report.py test-welcome --user-id 123456789 --username alice
python scripts/send_telegram_report.py test-admin --payload "src_xacc_uae_001_uae_goldhook_20260624"
```

#### Edge case handling

| Case | `parse_status` | Stage | Behavior |
| ---- | -------------- | ----- | -------- |
| No payload | `missing_payload` | New X Visitor | `country_target=unknown` |
| Unknown X account | `unknown_source` | Telegram Joined | Lead captured, source preserved |
| Invalid campaign | `invalid` | Telegram Joined | `campaign_id` cleared |
| Unknown country | `unknown_country` | Telegram Joined | Lead captured |
| Duplicate user | `ok` (+ flag) | Telegram Joined | Update row, `is_duplicate=true` |
| DB error | — | — | `activity_logs` failure, exception raised |
| Telegram fail | — | — | `activity_logs` failure, DB retained |

### 4. TEST

#### Valid payload

```bash
python scripts/sync_to_supabase.py test-join --payload "src_xacc_uae_001_uae_goldhook_20260624"
```

Expected: `parse_status: ok`, stage `Telegram Joined`, `source_account: xacc_uae_001`

#### Missing payload

```bash
python scripts/sync_to_supabase.py test-join --payload ""
```

Expected: `parse_status: missing_payload`, `country_target: unknown`, stage `New X Visitor`

#### Invalid campaign

```bash
python scripts/sync_to_supabase.py test-join --payload "src_xacc_uae_001_uae_bad_campaign_999"
```

Expected: `parse_status: invalid`, `campaign_id: null`

#### Unknown country

```bash
python scripts/sync_to_supabase.py test-join --payload "src_xacc_uae_001_japan_goldhook_20260624"
```

Expected: `parse_status: unknown_country`

#### Duplicate join

Run `test-join` twice with same `TEST_TELEGRAM_USER_ID`. Second run: `is_duplicate: true`.

#### Full capture with Telegram (requires `.env`)

```bash
python scripts/sync_to_supabase.py capture-start --user-id YOUR_ID --username you --payload "src_xacc_uae_001_uae_goldhook_20260624"
```

Verify admin chat receives source summary.

### 5. REVIEW

| Check | Status |
| ----- | ------ |
| Correctness — parse, validate, upsert, notify | ✓ |
| Readability — skill YAML documents full flow | ✓ |
| Architecture — Supabase SoT, Telegram as capture channel only | ✓ |
| Security — tokens in `.env` only | ✓ |
| Resilience — Telegram failures logged, DB not rolled back | ✓ |

### 6. SHIP

**Launch checklist (Phase 1):**

- [ ] `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_CHAT_ID` set
- [ ] Bot webhook points to Hermes Agent 1 handler (or CLI/cron bridge)
- [ ] Deep links use `src_{x_account}_{country}_{campaign}` format
- [ ] Valid `/start` creates attributed `telegram_joins` row
- [ ] Missing `/start` creates `unknown` attribution
- [ ] Duplicate joins update, not duplicate spam
- [ ] Admin receives join summary
- [ ] `activity_logs` records Telegram failures

**Suggested commit:**

```bash
git commit -m "done: phase1 telegram-biolink-ref-attribution"
```

---

## Phase 2 — Twenty CRM Pipeline

**Status:** Complete (code) — cần test Twenty live  
**Depends on:** Phase 0, Phase 1  
**ADR:** [002-crm-twenty-over-espocrm.md](adr/002-crm-twenty-over-espocrm.md)  
**Skill:** `skills/agent4-twenty-crm-sync.yaml`

### 1. SPEC

| Item | Definition |
| ---- | ---------- |
| **Requirement** | Twenty CRM thay EspoCRM cho pipeline visibility |
| **Source of truth** | Supabase — Twenty chỉ mirror |
| **Inputs** | Lead row từ Supabase (`leads`) |
| **Outputs** | Twenty Person + Opportunity, `crm_stage_events`, `activity_logs` |
| **Acceptance** | 1 lead sync; stage change cập nhật Twenty; API fail → log |
| **Failure cases** | Twenty down, stage enum mismatch, missing API key |

### 2. PLAN

**Affected files:**

```
skills/agent4-twenty-crm-sync.yaml
skills/agent4-crm-sync.yaml          # LEGACY — do not extend
config/twenty-pipeline.json
scripts/sync_to_twenty.py
docs/sop-ops.md
docs/runbook.md
docs/bundle-manifest.md
docs/launch-checklist.md
docs/rollback-plan.md
```

### 3. BUILD

```bash
python scripts/sync_to_twenty.py health
python scripts/sync_to_twenty.py test-sync --dry-run
python scripts/sync_to_twenty.py sync-lead --telegram-user-id 999000001   # thêm --live khi có Twenty
```

Pipeline stages: xem `config/twenty-pipeline.json`

### 4. TEST

| Test | Lệnh | Expected |
| ---- | ---- | -------- |
| Dry-run | `test-sync --dry-run` | JSON success, không gọi API |
| Health | `health` | `stages: 8`, env flags |
| Live sync | `sync-lead --telegram-user-id ID` + `--live` | `twenty_person_id` trong `leads.raw_payload` |
| Stage event | Sau sync | Row trong `crm_stage_events`, `twenty_synced=true` |
| API fail | Sai `TWENTY_API_KEY` | `activity_logs` status=failure |

### 5. REVIEW

| Check | Status |
| ----- | ------ |
| Supabase SoT — Twenty không ghi ngược | ✓ |
| EspoCRM deprecated, không extend | ✓ |
| crm_stage_events + activity_logs | ✓ |
| Agent 5 bundle updated | ✓ |

### 6. SHIP

**Agent 5 packaging (đã chạy):**

- [x] `bundle-manifest.md` — Twenty config + skill Agent 4
- [x] `runbook.md` — mục Phase 2
- [x] `launch-checklist.md` — tick partial Phase 2
- [x] `rollback-plan.md` — Twenty rollback
- [x] `agent5-monitor.yaml` — bundle workflow

**Suggested commit:**

```bash
git commit -m "done: phase2 twenty-crm-pipeline-sync"
```

---

## Phase 3 — Metabase Founder Dashboard

**Status:** Complete  
**Depends on:** Phase 0  
**ADR:** [003-dashboard-metabase.md](adr/003-dashboard-metabase.md)  
**Spec:** `config/metabase-dashboard-spec.md`

### 1. SPEC

| Item | Definition |
| ---- | ---------- |
| **Requirement** | Founder dashboard 1 màn hình — growth, country, vendor, content, funnel, purgatory, Apify, health |
| **Source of truth** | Supabase SQL views — Metabase chỉ visualize |
| **Inputs** | Tables Phase 0–2 + `apify_posts`, `country_intelligence`, `daily_kpis` |
| **Outputs** | `config/metabase-dashboard-spec.md` + 15 SQL views |
| **Acceptance** | Views deploy OK; spec đủ 8 sections; không Google Sheet |
| **Failure cases** | View lỗi SQL, Metabase không connect SSL, empty data |

### 2. PLAN

**Affected files:**

```
config/metabase-dashboard-spec.md
db/views.sql
docs/sop-ops.md
docs/runbook.md
docs/bundle-manifest.md
docs/launch-checklist.md
```

**Views mới (Phase 3):**

- `v_growth_overview` — KPI snapshot
- `v_x_account_performance` — join theo X account
- `v_campaign_performance` — cost per join
- `v_content_leaderboard` — top hook/hashtag/angle
- `v_apify_crawl_health` — crawl runs
- `v_country_intelligence_summary` — intel quality
- `v_crm_conversion` — conversion %
- `v_daily_kpis_dashboard` — rollup daily_kpis

**Cập nhật:** `v_purgatory_dashboard` — thêm `country_crawl_no_data`

### 3. BUILD

```bash
psql "$DATABASE_URL" -f db/views.sql
```

Đọc spec và tạo dashboard Metabase UI theo 8 sections trong `config/metabase-dashboard-spec.md`.

### 4. TEST

```sql
-- Smoke test tất cả views
SELECT 'v_growth_overview' AS v, COUNT(*) FROM v_growth_overview
UNION ALL SELECT 'v_daily_growth', COUNT(*) FROM v_daily_growth
UNION ALL SELECT 'v_country_performance', COUNT(*) FROM v_country_performance
UNION ALL SELECT 'v_vendor_performance', COUNT(*) FROM v_vendor_performance
UNION ALL SELECT 'v_content_performance', COUNT(*) FROM v_content_performance
UNION ALL SELECT 'v_content_leaderboard', COUNT(*) FROM v_content_leaderboard
UNION ALL SELECT 'v_crm_stage_funnel', COUNT(*) FROM v_crm_stage_funnel
UNION ALL SELECT 'v_crm_conversion', COUNT(*) FROM v_crm_conversion
UNION ALL SELECT 'v_purgatory_dashboard', COUNT(*) FROM v_purgatory_dashboard
UNION ALL SELECT 'v_apify_crawl_health', COUNT(*) FROM v_apify_crawl_health
UNION ALL SELECT 'v_country_intelligence_summary', COUNT(*) FROM v_country_intelligence_summary
UNION ALL SELECT 'v_system_health', COUNT(*) FROM v_system_health
UNION ALL SELECT 'v_x_account_performance', COUNT(*) FROM v_x_account_performance
UNION ALL SELECT 'v_campaign_performance', COUNT(*) FROM v_campaign_performance
UNION ALL SELECT 'v_daily_kpis_dashboard', COUNT(*) FROM v_daily_kpis_dashboard;
```

Expected: mỗi view trả về ≥0 rows, **không error**.

### 5. REVIEW

| Check | Status |
| ----- | ------ |
| 8 dashboard sections trong spec | ✓ |
| 15 views documented | ✓ |
| Purgatory 6 alert types | ✓ |
| No Google Sheet dependency | ✓ |
| Agent 5 bundle updated | ✓ |

### 6. SHIP

**Agent 5 packaging:**

- [x] `bundle-manifest.md` — Metabase spec ✅
- [x] `runbook.md` — Phase 3 Metabase setup
- [x] `launch-checklist.md` — Phase 3 items

**Suggested commit:**

```bash
git commit -m "done: phase3 metabase-founder-dashboard-spec"
```

---

## Phase 4 — Apify / Country Intelligence

**Status:** Complete (code) — live crawl cần `APIFY_API_TOKEN`  
**Depends on:** Phase 0  
**Skill:** `skills/agent3-daily-loop.yaml`

### 1. SPEC

| Item | Definition |
| ---- | ---------- |
| **Requirement** | Daily XAUUSD/gold intelligence theo country + hashtag |
| **Actor** | Apify `EvFXOhwR6wsOWmdSK` |
| **Inputs** | Apify dataset hoặc `--sample` (22 posts Canada #xauusd) |
| **Outputs** | `apify_posts`, `country_intelligence`, Telegram report, `system_health_logs` |
| **Categories** | signal, proof, education, promo, noise |
| **Acceptance** | 20+ posts classified, 5+ hooks, intel row, admin report, health log |

### 2. PLAN

**Affected files:**

```
config/apify-xauusd-crawl.json
scripts/run_apify_crawl.py
scripts/normalize_apify_dataset.py
scripts/send_telegram_report.py      # country-report
prompts/apify-classify-post.txt
prompts/apify-hook-extract.txt
prompts/country-opportunity-report.txt
skills/agent3-daily-loop.yaml
docs/sop-ops.md, runbook, bundle-manifest, launch-checklist
```

**Cron (Agent 3):**

| Time | Task |
| ---- | ---- |
| 06:00 | Apify country crawl |
| 07:00 | Affiliate/vendor checklist (planned) |
| 14:00 | Coaching if drop (planned) |
| 21:00 | Country + founder report |

### 3. BUILD

```bash
python scripts/run_apify_crawl.py health
python scripts/normalize_apify_dataset.py --sample --dry-run
python scripts/run_apify_crawl.py test-canada              # DB + report (cần DATABASE_URL)
python scripts/run_apify_crawl.py test-canada --report      # + Telegram admin
python scripts/send_telegram_report.py country-report --dry-run
python scripts/run_apify_crawl.py run --country Canada --hashtag "#xauusd" --max-items 50
```

### 4. TEST

| Test | Lệnh | Expected |
| ---- | ---- | -------- |
| Dry-run classify | `normalize --sample --dry-run` | 22 posts, 16+ hooks, 7 High |
| Health | `run_apify_crawl.py health` | actor_id, countries count |
| DB insert | `test-canada` (no --dry-run) | rows in `apify_posts`, `country_intelligence` |
| Health log | After test-canada | `system_health_logs` service=apify_crawl |
| Telegram | `country-report --dry-run` | HTML report formatted |

```sql
SELECT COUNT(*), category FROM apify_posts GROUP BY category;
SELECT * FROM country_intelligence WHERE country_target = 'Canada' ORDER BY report_date DESC LIMIT 1;
SELECT * FROM system_health_logs WHERE service_name = 'apify_crawl' ORDER BY checked_at DESC LIMIT 1;
```

### 5. REVIEW

| Check | Status |
| ----- | ------ |
| 8 countries + 2 hashtags in config | ✓ |
| Rule-based classify + prompt templates | ✓ |
| country_intelligence đủ fields brief | ✓ |
| activity_logs + system_health on fail | ✓ |
| Agent 5 bundle updated | ✓ |

### 6. SHIP

**Agent 5 packaging:**

- [x] `bundle-manifest.md` — Apify config, prompts, Agent 3 skill
- [x] `runbook.md` — Phase 4
- [x] `launch-checklist.md` — Phase 4 items

**Suggested commit:**

```bash
git commit -m "done: phase4 apify-last30days-country-intelligence"
```

---

## Phase 5 — Content Performance Tracker

**Status:** Complete  
**Depends on:** Phase 0, Phase 1

### 1. SPEC

| Item | Definition |
| ---- | ---------- |
| **Requirement** | Track content post → clicks → Telegram joins → join_rate |
| **Table** | `content_performance` (+ `content_assets`) |
| **Statuses** | draft, assigned, posted, tracked, winning, failed, archived |
| **join_rate** | `telegram_joins / clicks` (generated column) |
| **Attribution** | Deep link `src_..._{campaign}_{content_id}` → auto increment joins |

### 2. PLAN

**Affected files:** `db/schema.sql`, `db/views.sql`, `db/seed_stages.sql`, `scripts/sync_to_supabase.py`, `config/metabase-dashboard-spec.md`, docs

**Views mới:** `v_winning_content`, `v_content_status_summary` (+ enhanced `v_content_performance`)

### 3. BUILD

```bash
python scripts/sync_to_supabase.py content-insert --content-id hook001 \
  --post-url "https://x.com/hermes_gold_uae/status/1" \
  --x-account xacc_uae_001 --country uae --campaign goldhook_20260624 \
  --hook "Gold breakout 2350" --angle breakout --hashtag "#xauusd" \
  --clicks 100 --status posted

python scripts/sync_to_supabase.py content-metrics --content-id hook001 \
  --clicks 200 --telegram-joins 10

python scripts/sync_to_supabase.py content-mark-winning --content-id hook001

python scripts/sync_to_supabase.py test-join \
  --payload "src_xacc_uae_001_uae_goldhook_20260624_hook001"

python scripts/sync_to_supabase.py content-test
```

### 4. TEST

| Test | Expected |
| ---- | -------- |
| `content-insert` | Row in `content_performance`, status=posted |
| `content-metrics` | clicks/joins updated, `join_rate` recalculated |
| `content-mark-winning` | status=winning, `content_assets.status=winning` |
| Join with content_id | `telegram_joins` +1, status→tracked |
| `v_content_performance` | Returns performance_tier |

```sql
SELECT content_id, clicks, telegram_joins, join_rate, status FROM content_performance WHERE content_id = 'hook001';
SELECT * FROM v_winning_content;
SELECT * FROM v_content_status_summary;
```

### 5. REVIEW

| Check | Status |
| ----- | ------ |
| insert + update metrics API-ready (CLI) | ✓ |
| join_rate generated | ✓ |
| Winning reusable via v_winning_content | ✓ |
| Metabase spec Section 4 updated | ✓ |
| Agent 5 bundle updated | ✓ |

### 6. SHIP

**Suggested commit:**

```bash
git commit -m "done: phase5 content-performance-tracker"
```

---

## Phase 6 — Plane Vendor / Content Board

**Status:** Complete  
**Depends on:** Phase 4, Phase 5  
**Spec:** `config/plane-board-spec.md`

### 1. SPEC

| Item | Definition |
| ---- | ---------- |
| **Requirement** | Board vận hành cho team Tuấn — content production |
| **Tool** | Plane (UI) + `vendor_tasks` (Supabase mirror) |
| **Columns** | Backlog → Ready → Assigned → Posted → Need Fix → Winning → Archived |
| **Acceptance** | Tạo test task; Apify High → task; `plane_task_id` lưu DB; sync-status documented |

### 2. PLAN

```
config/plane-board-spec.md
config/plane-board.json
scripts/create_plane_task.py
docs/sop-ops.md, runbook, bundle-manifest, launch-checklist
```

### 3. BUILD

```bash
python scripts/create_plane_task.py health
python scripts/create_plane_task.py create \
  --country UAE --hashtag "#xauusd" --angle breakout \
  --hook "Gold breakout 2350" --x-account xacc_uae_001 --dry-run

python scripts/create_plane_task.py test                    # vendor_tasks local
python scripts/create_plane_task.py from-apify --local-only --limit 1
python scripts/create_plane_task.py from-winning --content-id hook001 --local-only --dry-run
python scripts/create_plane_task.py sync-status --vendor-task-id <uuid> --dry-run
```

### 4. TEST

| Test | Expected |
| ---- | -------- |
| `create --dry-run` | JSON body với title `[UAE] #xauusd breakout` |
| `test` | Row trong `vendor_tasks`, `source=phase6_test` |
| `from-apify --local-only` | Task từ `apify_posts` lead_potential=High |
| Live + Plane | `plane_task_id` populated |

```sql
SELECT id, plane_task_id, title, status, country_target FROM vendor_tasks ORDER BY created_at DESC LIMIT 5;
```

### 5. REVIEW

| Check | Status |
| ----- | ------ |
| Task template đủ fields brief | ✓ |
| SOP team Tuấn (spec §7) | ✓ |
| activity_logs on create fail | ✓ |
| sync-status stub for Phase 7 | ✓ |

### 6. SHIP

**Suggested commit:**

```bash
git commit -m "done: phase6 plane-vendor-content-board"
```

---

## Phase 7 — Activepieces Automation Bridge

**Status:** Complete (spec + test script)  
**Depends on:** Phase 1–6  
**ADR:** [004-automation-activepieces-before-n8n.md](adr/004-automation-activepieces-before-n8n.md)  
**Spec:** `config/activepieces-flows-spec.md`

### 1. SPEC

| Item | Definition |
| ---- | ---------- |
| **Requirement** | No-code automation bridge thay Zapier — 6 flows |
| **Platform** | Activepieces first; **không n8n** trong MVP |
| **SoT** | Supabase — Activepieces chỉ trigger/action |
| **Failure** | Mọi flow fail → `activity_logs` (`source=automation`) |
| **Acceptance** | Spec đủ 6 flows; webhook test documented; log-failure works |

### 2. PLAN

```
config/activepieces-flows-spec.md
config/activepieces-flows.json
scripts/activepieces_webhook_test.py
docs/sop-ops.md, runbook, bundle-manifest, launch-checklist
```

### 3. BUILD — 6 flows

| # | Flow | Trigger | Action |
| - | ---- | ------- | ------ |
| 1 | New Telegram Join | `telegram_joins` INSERT | Twenty sync + admin notify |
| 2 | Stage Changed | `crm_stage_events` INSERT | Telegram follow-up + Twenty |
| 3 | High Apify Post | `apify_posts` High | Create Plane task |
| 4 | Daily KPI | Cron 21:00 / `daily_kpis` | Founder report |
| 5 | Vendor Overdue | Cron hourly | Admin alert |
| 6 | Renewal Risk | Cron daily | Stage Renewal Risk + nurture |

### 4. TEST

```bash
python scripts/activepieces_webhook_test.py health
python scripts/activepieces_webhook_test.py sample-payload --flow 1
python scripts/activepieces_webhook_test.py send --flow 1 --dry-run
python scripts/activepieces_webhook_test.py log-failure --flow 1 --message "test"
python scripts/activepieces_webhook_test.py test
```

Live webhook (cần `ACTIVEPIECES_WEBHOOK_FLOW1`):

```bash
python scripts/activepieces_webhook_test.py send --flow 1
```

```sql
SELECT * FROM activity_logs WHERE source = 'automation' ORDER BY created_at DESC LIMIT 5;
```

### 5. REVIEW

| Check | Status |
| ----- | ------ |
| 6 flows trigger/action/payload | ✓ |
| Failure logging pattern | ✓ |
| Not source of truth | ✓ |
| n8n not installed | ✓ |
| Agent 5 bundle updated | ✓ |

### 6. SHIP

**Suggested commit:**

```bash
git commit -m "done: phase7 activepieces-automation-bridge-spec"
```

---

---

## Phase 8 — Agent 5 Monitor / Operating Rhythm

**Status:** SHIP (code + docs)

### Mục tiêu

- Monitor toàn stack: Hermes, Supabase, Telegram, Twenty, Metabase, Plane, Activepieces, Apify, VPS, GitHub
- Báo cáo founder **20:00** (7 sections) qua Telegram
- Weekly review SOP (Thứ 2 09:00)
- `system_health_logs` persist mỗi 30 phút
- Agent 5 bundle manifest cập nhật sau phase

### Scripts

| Command | Mô tả |
|---------|--------|
| `python scripts/health_check.py` | JSON health tất cả services |
| `python scripts/health_check.py --persist` | Ghi `system_health_logs` |
| `python scripts/health_check.py founder-data` | Metrics cho báo cáo 8PM |
| `python scripts/health_check.py weekly-review` | Weekly review JSON |
| `python scripts/health_check.py bundle` | Verify SOP bundle files |
| `python scripts/send_telegram_report.py founder-daily --dry-run` | Preview founder report |
| `python scripts/send_telegram_report.py founder-daily` | Gửi Telegram admin 20:00 |
| `python scripts/send_telegram_report.py founder-daily --weekly` | Weekly review Telegram |

### Founder daily report (7 sections)

1. **Growth** — joins hôm nay, 7d, top country
2. **CRM funnel** — stage counts, purgatory, weakest stage
3. **Content** — top hook, join rate, winning count
4. **Apify** — country intel mới nhất, crawl status
5. **Vendor ops** — Plane tasks open/done
6. **System health** — overall + failed services
7. **Action items** — từ `v_action_items` + automation errors 24h

Template: `prompts/report-founder.txt`

### Weekly review (Thứ 2)

- Top winning country / hook / vendor
- Weakest CRM stage
- Cost per join trend (nếu có spend data)
- Content to repeat, accounts to pause
- Next week priority

### Cron (Hermes / VPS)

```cron
*/30 * * * *  python scripts/health_check.py --persist
0 20 * * *    python scripts/send_telegram_report.py founder-daily
0 9 * * 1     python scripts/send_telegram_report.py founder-daily --weekly
```

### GitHub monitor

- Nếu `.git` tồn tại: `git log -1` → last commit trong health JSON
- Không có repo local: `status: documented_pending`
- `GITHUB_MONITOR_ENABLED=false` để tắt

### Failed services

Báo cáo founder hiển thị rõ `⚠️ Failed: service1, service2` khi `overall != healthy`.

### Test Phase 8

```bash
python scripts/health_check.py
python scripts/health_check.py founder-data
python scripts/health_check.py weekly-review
python scripts/health_check.py bundle
python scripts/send_telegram_report.py founder-daily --dry-run
```

---

## Phase 9 — E2E Launch Test

**Status:** SHIP (code + docs)

### Mục tiêu

- Mô phỏng lead journey end-to-end trong một lệnh
- Verify 12 bước: foundation → capture → content → CRM → Apify → Plane → Activepieces → views → monitor → rhythm → activity_logs → stack health
- `rollback-plan.md` reviewed
- Launch checklist Phase 9 code items ticked

### Script

```bash
python scripts/e2e_launch_test.py
python scripts/e2e_launch_test.py --report e2e-report.json
python scripts/e2e_launch_test.py --live-twenty   # optional Twenty live sync
```

**Exit code 0** khi `summary.launch_ready=true` (tất cả steps pass + DATABASE_URL set).

### 12 E2E steps

| Step | Mô tả |
| ---- | ----- |
| 1 | `sync_to_supabase.py health` |
| 2 | `test-join` với payload có `content_id` |
| 3 | `content-test` |
| 4 | Twenty `test-sync --dry-run` (hoặc `--live-twenty`) |
| 5 | Apify `normalize --sample --dry-run` |
| 6 | `create_plane_task.py test` |
| 7 | `activepieces_webhook_test.py test` |
| 8 | 6 dashboard views queryable |
| 9 | `health_check.py bundle` |
| 10 | `founder-daily --dry-run` |
| 11 | Không critical failure trong `activity_logs` 24h |
| 12 | Overall health ≠ down |

### Production go-live (ngoài repo)

Các mục trong `launch-checklist.md` (Telegram bot live, Twenty stages UI, Metabase cards, Activepieces publish) do operator hoàn tất trên production.

### SHIP commit

```bash
git commit -m "done: phase9 e2e-launch-test"
```

---

## Phase 10 — SOP Bundle Hoàn Chỉnh

**Status:** SHIP

### Deliverables

| File | Mô tả |
| ---- | ----- |
| `README.md` | Setup, quick start, cron, doc map |
| `CLAUDE.md` | AI assistant project rules v2 |
| `docs/case-study-mapping.md` | Case study → module mapping |
| `skills/agent2-onboard.yaml` | Skill #2 (D1–D7 MVP documented) |
| `docs/bundle-manifest.md` | 100% ✅ |

### Verify bundle

```bash
python scripts/health_check.py bundle
python scripts/e2e_launch_test.py
```

### Quy tắc tái sử dụng ngành khác

**Đổi:** copy, countries, hashtags, stages, qualification  
**Giữ:** 5 skills, Supabase SoT, CRM/dashboard/board/automation pattern, Agent 5 rhythm

### SHIP commit

```bash
git commit -m "done: phase10 sop-bundle-complete"
```

---

## Architecture ADRs

| ADR | Decision |
| --- | -------- |
| [001](adr/001-source-of-truth-supabase.md) | Supabase/Postgres as source of truth |
| [002](adr/002-crm-twenty-over-espocrm.md) | Twenty CRM over EspoCRM |
| [003](adr/003-dashboard-metabase.md) | Metabase for founder dashboard |
| [004](adr/004-automation-activepieces-before-n8n.md) | Activepieces before n8n |
| [005](adr/005-one-hermes-five-skills.md) | 1 Hermes instance, 5 skill files |

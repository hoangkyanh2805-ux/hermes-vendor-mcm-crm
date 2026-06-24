# Activepieces Automation Flows Spec
# MCM Vendor — Hermes XAUUSD Growth OS v2 — Phase 7

**ADR:** [docs/adr/004-automation-activepieces-before-n8n.md](../docs/adr/004-automation-activepieces-before-n8n.md)  
**Machine config:** [activepieces-flows.json](activepieces-flows.json)

> Activepieces là **cầu nối automation**, không phải source of truth.  
> Mọi failure phải ghi `activity_logs` (`actor=activepieces`, `source=automation`).

---

## 1. Setup Activepieces

### Env

```env
ACTIVEPIECES_API_URL=https://your-activepieces.example.com/api/v1
ACTIVEPIECES_API_KEY=
ACTIVEPIECES_WEBHOOK_SECRET=          # optional HMAC verify

# Per-flow incoming webhook URLs (copy from Activepieces UI after publish)
ACTIVEPIECES_WEBHOOK_FLOW1=
ACTIVEPIECES_WEBHOOK_FLOW2=
ACTIVEPIECES_WEBHOOK_FLOW3=
ACTIVEPIECES_WEBHOOK_FLOW4=
ACTIVEPIECES_WEBHOOK_FLOW5=
ACTIVEPIECES_WEBHOOK_FLOW6=
```

### Nguyên tắc

| Rule | Chi tiết |
| ---- | -------- |
| SoT | Supabase — Activepieces chỉ trigger/action |
| Failure | HTTP step cuối hoặc `log-failure` script → `activity_logs` |
| Idempotent | Dùng `lead_id` / `telegram_user_id` dedupe trong flow |
| n8n | **Không cài** trong MVP |

---

## 2. Flow 1 — New Telegram Join

**Mục tiêu:** Join mới → Twenty sync + admin alert (nếu Agent 1 chưa làm hết).

### Trigger

| Option | Config |
| ------ | ------ |
| A (khuyến nghị) | Supabase Database Webhook: `INSERT` on `telegram_joins` |
| B | HTTP Webhook từ Hermes Agent 1 sau `capture_telegram_start` |

### Sample payload (Supabase webhook)

```json
{
  "type": "INSERT",
  "table": "telegram_joins",
  "record": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "lead_id": "660e8400-e29b-41d4-a716-446655440001",
    "telegram_user_id": 123456789,
    "telegram_username": "goldtrader_uae",
    "start_payload": "src_xacc_uae_001_uae_goldhook_20260624_hook001",
    "source_account": "xacc_uae_001",
    "country_target": "uae",
    "campaign_id": "goldhook_20260624",
    "content_id": "hook001",
    "parse_status": "ok",
    "is_duplicate": false,
    "join_time": "2026-06-24T12:00:00Z"
  }
}
```

### Actions (Activepieces steps)

1. **Filter:** `is_duplicate = false`
2. **HTTP Request — Twenty sync**  
   - Method: `POST` (hoặc gọi VPS script)  
   - URL: `{HERMES_VPS}/internal/sync-twenty`  
   - Body: `{ "lead_id": "{{record.lead_id}}" }`  
   - Fallback CLI: `python scripts/sync_to_twenty.py sync-lead --lead-id {{lead_id}}`
3. **Telegram — Admin notify** (skip nếu Agent 1 đã gửi)  
   - Chat: `TELEGRAM_ADMIN_CHAT_ID`  
   - Text: template từ `send_telegram_report.format_admin_join_alert`
4. **On error → Log failure**  
   - `python scripts/activepieces_webhook_test.py log-failure --flow 1 --message "..."`

### Test

```bash
python scripts/activepieces_webhook_test.py sample-payload --flow 1
python scripts/activepieces_webhook_test.py send --flow 1 --dry-run
python scripts/activepieces_webhook_test.py send --flow 1   # cần ACTIVEPIECES_WEBHOOK_FLOW1
```

---

## 3. Flow 2 — Stage Changed

**Mục tiêu:** Stage đổi trên Supabase → Twenty update + Telegram follow-up/admin.

### Trigger

Supabase webhook: `INSERT` on `crm_stage_events`

### Sample payload

```json
{
  "type": "INSERT",
  "table": "crm_stage_events",
  "record": {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "lead_id": "660e8400-e29b-41d4-a716-446655440001",
    "from_stage": "Telegram Joined",
    "to_stage": "Warm Member",
    "reason": "stage_change",
    "triggered_by": "trigger",
    "twenty_synced": false
  }
}
```

### Actions

1. **Branch** theo `to_stage`:
   - `Signal Interested` → Telegram DM template VIP
   - `Trial / Consult` → admin notify
   - `Paid / VIP` → admin celebrate
   - `Renewal Risk` → nurture (overlap Flow 6)
2. **HTTP — Twenty sync** nếu `twenty_synced = false`
3. **Log failure** on any step error

---

## 4. Flow 3 — High Potential Apify Post

**Mục tiêu:** Post Apify `lead_potential=High` → tạo Plane task cho Tuấn.

### Trigger

| Option | Filter |
| ------ | ------ |
| Supabase INSERT `apify_posts` | `lead_potential = 'High'` |
| Cron sau crawl 06:30 | Query `apify_posts` last 1h High |

### Sample payload

```json
{
  "type": "INSERT",
  "table": "apify_posts",
  "record": {
    "id": "880e8400-e29b-41d4-a716-446655440003",
    "country_target": "Canada",
    "hashtag": "#xauusd",
    "post_url": "https://x.com/trader/status/123",
    "hook_extracted": "Gold breakout above 2350",
    "content_angle": "breakout",
    "lead_potential": "High",
    "engagement_score": 142.5
  }
}
```

### Actions

1. **HTTP / SSH script:**  
   `python scripts/create_plane_task.py from-apify --local-only --limit 1`  
   Hoặc POST JSON tới internal API với fields trên
2. **Telegram admin:** "New Plane task from Apify High post"
3. **Log failure**

---

## 5. Flow 4 — Daily KPI Ready

**Mục tiêu:** 21:00 founder report (mở rộng Agent 5 Phase 8).

### Trigger

| Option | Schedule |
| ------ | -------- |
| Activepieces Cron | `0 21 * * *` |
| Supabase INSERT `daily_kpis` | khi Agent 5 rollup xong |

### Sample payload

```json
{
  "type": "INSERT",
  "table": "daily_kpis",
  "record": {
    "kpi_date": "2026-06-24",
    "telegram_joins": 42,
    "top_country": "uae",
    "top_x_account": "xacc_uae_001",
    "paid_vip": 3,
    "renewal_risk": 5,
    "apify_posts_crawled": 120,
    "vendor_tasks_overdue": 2
  }
}
```

### Actions

1. **HTTP script:** `python scripts/send_telegram_report.py country-report` (Phase 8: `report-founder`)
2. **Optional:** Metabase screenshot link in message
3. **Log failure**

---

## 6. Flow 5 — Vendor Task Overdue

**Mục tiêu:** Task quá deadline → alert admin.

### Trigger

Activepieces Cron: `0 * * * *` (mỗi giờ)

### Poll query (HTTP → Supabase REST hoặc script)

```sql
SELECT id, title, country_target, deadline, status
FROM vendor_tasks
WHERE status IN ('assigned', 'ready_to_post')
  AND deadline < NOW();
```

### Sample payload (synthetic cron)

```json
{
  "flow": "vendor_task_overdue",
  "tasks": [
    {
      "id": "990e8400-e29b-41d4-a716-446655440004",
      "title": "[UAE] #xauusd breakout",
      "country_target": "uae",
      "deadline": "2026-06-23T18:00:00Z",
      "status": "assigned",
      "plane_task_id": "plane-uuid-123"
    }
  ]
}
```

### Actions

1. **Loop** tasks → Telegram admin: overdue list
2. **Update** `vendor_tasks.status = 'overdue'` (HTTP PATCH Supabase)
3. **Log failure**

---

## 7. Flow 6 — Renewal Risk

**Mục tiêu:** Member inactive > 3 ngày → stage Renewal Risk + nurture.

### Trigger

Activepieces Cron: `0 8 * * *`

### Poll query

```sql
SELECT m.id, m.lead_id, m.telegram_user_id, m.telegram_username,
       COALESCE(m.last_active_at, m.join_time) AS last_active
FROM members m
WHERE COALESCE(m.last_active_at, m.join_time) < NOW() - INTERVAL '3 days'
  AND m.current_stage NOT IN ('Churned', 'Renewal Risk');
```

### Sample payload

```json
{
  "flow": "renewal_risk",
  "members": [
    {
      "lead_id": "660e8400-e29b-41d4-a716-446655440001",
      "telegram_user_id": 123456789,
      "telegram_username": "goldtrader_uae",
      "days_inactive": 5
    }
  ]
}
```

### Actions

1. **Supabase PATCH** `leads` + `members` → `current_stage = 'Renewal Risk'`
2. **Telegram DM** nurture template (prompts/coaching.txt Phase 8)
3. **crm_stage_events** insert (hoặc để DB trigger tự ghi)
4. **Twenty sync** via Flow 2 chain
5. **Log failure**

---

## 8. Failure logging pattern

Mọi flow phải có nhánh **On failure**:

```bash
python scripts/activepieces_webhook_test.py log-failure \
  --flow 3 \
  --message "Plane task create failed" \
  --error "HTTP 500 from create_plane_task" \
  --entity-id "{{apify_post_id}}"
```

Ghi vào `activity_logs`:

| Field | Value |
| ----- | ----- |
| entity_type | `automation` / table name |
| action | `activepieces_flow_{N}` |
| status | `failure` |
| actor | `activepieces` |
| source | `automation` |

Verify:

```sql
SELECT * FROM activity_logs
WHERE source = 'automation'
ORDER BY created_at DESC LIMIT 10;
```

---

## 9. Supabase webhook setup

1. Supabase Dashboard → Database → Webhooks
2. Target URL = Activepieces flow webhook URL
3. Tables: `telegram_joins`, `crm_stage_events`, `apify_posts`, `daily_kpis`
4. HTTP headers: `Authorization: Bearer {ACTIVEPIECES_WEBHOOK_SECRET}` nếu cần

---

## 10. Activepieces ↔ Hermes VPS

Nếu scripts chạy trên cùng VPS Hermes:

| Flow | Command |
| ---- | ------- |
| 1 | `sync_to_twenty.py sync-lead --lead-id $ID` |
| 3 | `create_plane_task.py from-apify --local-only` |
| 4 | `send_telegram_report.py country-report` |
| 5 | query + `send_telegram_report` custom overdue template |

Wrap bằng Activepieces **Webhook → Code → HTTP** hoặc **SSH** piece (self-hosted).

---

## 11. Acceptance checklist

- [x] Spec covers 6 flows với trigger/action/payload
- [x] `activepieces_webhook_test.py` — sample + send + log-failure
- [x] Failure → `activity_logs` documented + script
- [x] Activepieces = bridge, Supabase = SoT
- [ ] **Ops:** publish 6 flows trên Activepieces instance
- [ ] **Ops:** 1 live webhook test (Flow 1 recommended)

---

## 12. Phase 8 handoff

- Agent 5 `health_check.py` thêm Activepieces flow status poll
- Founder report template → `prompts/report-founder.txt`
- Plane webhook → `sync-status` thay cron manual

---

*Phase 7 — spec + webhook test; flows built manually in Activepieces UI per this doc.*

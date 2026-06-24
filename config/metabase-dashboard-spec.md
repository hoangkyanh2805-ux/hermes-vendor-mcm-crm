# Metabase Founder Dashboard Spec
# MCM Vendor — Hermes XAUUSD Growth OS v2 — Phase 3

**Data source:** Supabase/Postgres (`DATABASE_URL`) — **không dùng Google Sheet**  
**ADR:** [docs/adr/003-dashboard-metabase.md](../docs/adr/003-dashboard-metabase.md)

---

## 1. Setup Metabase

### Kết nối database

1. Metabase → Admin → Databases → Add database
2. Engine: **PostgreSQL**
3. Host: Supabase pooler host (hoặc `db.<project>.supabase.co`)
4. Database name: `postgres`
5. User / password: từ Supabase
6. Schema: `public`
7. SSL: bật

### Env

```env
METABASE_URL=https://your-metabase.example.com
METABASE_API_KEY=...   # optional — cho automation Phase 8
```

### Deploy views trước khi tạo cards

```bash
psql "$DATABASE_URL" -f db/views.sql
```

---

## 2. Dashboard layout

Tạo 1 dashboard: **「MCM Growth OS — Founder」**  
8 tab/section (có thể 1 dashboard với text cards phân vùng, hoặc 8 sub-dashboards).

| # | Section | Primary view(s) |
| - | ------- | ---------------- |
| 1 | Growth Overview | `v_growth_overview`, `v_daily_growth`, `v_daily_kpis_dashboard` |
| 2 | Country Performance | `v_country_performance` |
| 3 | Vendor Performance | `v_vendor_performance` |
| 4 | Content Performance | `v_content_performance`, `v_content_leaderboard`, `v_winning_content`, `v_content_status_summary` |
| 5 | CRM Stage Funnel | `v_crm_stage_funnel`, `v_crm_conversion` |
| 6 | Purgatory Dashboard | `v_purgatory_dashboard` |
| 7 | Apify Crawl Health | `v_apify_crawl_health`, `v_country_intelligence_summary` |
| 8 | System Health | `v_system_health` |

---

## 3. Section 1 — Growth Overview

### Mục tiêu

Founder thấy trong 10 giây: hôm nay có bao nhiêu join, trend 7d/30d, top country/account/vendor, cost/join.

### Cards

| Card | Type | SQL / View | Visualization |
| ---- | ---- | ---------- | ------------- |
| Joins today | Number | `SELECT joins_today FROM v_growth_overview` | Scalar |
| Joins 7d | Number | `SELECT joins_7d FROM v_growth_overview` | Scalar |
| Joins 30d | Number | `SELECT joins_30d FROM v_growth_overview` | Scalar |
| Top country (30d) | Text | `SELECT top_country_30d FROM v_growth_overview` | Scalar |
| Top X account (30d) | Text | `SELECT top_x_account_30d FROM v_growth_overview` | Scalar |
| Top vendor (30d) | Text | `SELECT top_vendor_30d FROM v_growth_overview` | Scalar |
| Avg cost/join | Number | `SELECT avg_cost_per_join FROM v_growth_overview` | Scalar ($) |
| Joins by day | Line chart | `SELECT * FROM v_daily_growth ORDER BY growth_date` | X=`growth_date`, Y=`telegram_joins` |
| Attributed vs duplicate | Bar | `v_daily_growth` | `attributed_joins`, `duplicate_joins` |
| Join by X account | Table | `SELECT * FROM v_x_account_performance ORDER BY joins_7d DESC` | Table |
| Campaign cost | Table | `SELECT * FROM v_campaign_performance WHERE budget_usd IS NOT NULL` | Table |

### Sample SQL — joins by day

```sql
SELECT
    growth_date,
    telegram_joins,
    attributed_joins,
    duplicate_joins
FROM v_daily_growth
WHERE growth_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY growth_date;
```

---

## 4. Section 2 — Country Performance

| Card | Type | Query |
| ---- | ---- | ----- |
| Leads by country | Bar chart | `v_country_performance` — X=`country_target`, Y=`total_leads` |
| Paid VIP by country | Stacked bar | `paid_vip`, `churned` by `country_target` |
| Avg engagement | Table | `avg_engagement_score` DESC |
| Last join | Table | `last_join_time` |

```sql
SELECT
    country_target,
    total_leads,
    telegram_joined,
    paid_vip,
    churned,
    avg_engagement_score,
    last_join_time
FROM v_country_performance
ORDER BY total_leads DESC;
```

---

## 5. Section 3 — Vendor Performance

| Card | Type | Query |
| ---- | ---- | ----- |
| Leads per vendor | Bar | `v_vendor_performance.total_leads` |
| Converted leads | Bar | `converted_leads` |
| Overdue tasks | Number (red if > 0) | `SUM(overdue_tasks)` |
| Winning content | Table | `winning_content_count` DESC |

```sql
SELECT
    vendor_name,
    total_leads,
    converted_leads,
    total_tasks,
    overdue_tasks,
    winning_content_count
FROM v_vendor_performance
ORDER BY total_leads DESC;
```

---

## 6. Section 4 — Content Performance (Phase 5)

| Card | Type | Query |
| ---- | ---- | ----- |
| All content metrics | Table | `v_content_performance` |
| Performance tier | Bar | `performance_tier` counts from `v_content_performance` |
| Status pipeline | Funnel/bar | `v_content_status_summary` |
| Winning — reuse | Table | `v_winning_content` |
| Top hooks | Table | `v_content_leaderboard WHERE metric_type = 'hook'` |
| Join rate leaders | Table | `join_rate DESC`, `telegram_joins DESC` |
| Posted with zero joins | Table | `status = 'posted' AND telegram_joins = 0` |

```sql
SELECT content_id, hook, country_target, clicks, telegram_joins, join_rate, performance_tier, status
FROM v_content_performance
ORDER BY join_rate DESC, telegram_joins DESC;
```

```sql
SELECT * FROM v_winning_content;
```

```sql
SELECT status, content_count, total_joins, total_clicks, avg_join_rate
FROM v_content_status_summary;
```

**Attribution:** Telegram deep link `..._{campaign}_{content_id}` increments `telegram_joins` via Agent 1 capture.

---

## 7. Section 5 — CRM Stage Funnel

| Card | Type | Query |
| ---- | ---- | ----- |
| Funnel bar | Bar | `v_crm_stage_funnel` — X=`stage_name`, Y=`lead_count` |
| Avg days in stage | Table | `avg_days_in_stage` |
| Stale in stage (>3d) | Number | `SUM(stale_count)` |
| Conversion % | Table | `v_crm_conversion` |
| Bottleneck | Text | Stage có `avg_days_in_stage` cao nhất (custom SQL) |

```sql
SELECT
    stage_name,
    lead_count,
    avg_days_in_stage,
    stale_count
FROM v_crm_stage_funnel
ORDER BY sort_order;
```

```sql
-- Bottleneck alert
SELECT stage_name, avg_days_in_stage
FROM v_crm_stage_funnel
ORDER BY avg_days_in_stage DESC NULLS LAST
LIMIT 1;
```

---

## 8. Section 6 — Purgatory Dashboard

**Mục tiêu:** Mọi thứ bị "kẹt" — founder hành động ngay.

| Alert type | Ý nghĩa |
| ---------- | ------- |
| `stuck_stage` | Lead >7 ngày cùng stage |
| `inactive_member` | Member không active >3 ngày |
| `vendor_overdue` | Task quá deadline |
| `x_zero_joins` | X account active nhưng 0 join |
| `country_crawl_no_data` | Apify crawl không có data hữu ích |
| `automation_failure` | `activity_logs` failure 24h |

| Card | Type | Query |
| ---- | ---- | ----- |
| Purgatory table | Table (conditional formatting) | `SELECT * FROM v_purgatory_dashboard` |
| Count by alert type | Pie | `GROUP BY alert_type` |
| Critical (days_stuck > 7) | Number | Filter `days_stuck > 7` |

```sql
SELECT alert_type, COUNT(*) AS alert_count
FROM v_purgatory_dashboard
GROUP BY alert_type
ORDER BY alert_count DESC;
```

---

## 9. Section 7 — Apify Crawl Health

| Card | Type | Query |
| ---- | ---- | ----- |
| Last crawl | Text | `MAX(last_crawl_at) FROM v_apify_crawl_health` |
| Posts crawled | Number | Latest run `posts_crawled` |
| High potential | Number | `high_potential_posts` |
| Noise ratio | % | `noise_posts / NULLIF(posts_crawled,0)` |
| By country intel | Table | `v_country_intelligence_summary` |
| Low value countries | Table | `crawl_quality IN ('no_data','low_value')` |

```sql
SELECT *
FROM v_apify_crawl_health
ORDER BY last_crawl_at DESC
LIMIT 5;
```

---

## 10. Section 8 — System Health

| Card | Type | Query |
| ---- | ---- | ----- |
| Service status grid | Table | `v_system_health` |
| Down services | Number (red) | `COUNT(*) WHERE status IN ('down','degraded')` |
| Recent automation failures | Table | `activity_logs` failures 24h |

```sql
SELECT service_name, status, latency_ms, message, checked_at
FROM v_system_health
ORDER BY
    CASE status WHEN 'down' THEN 1 WHEN 'degraded' THEN 2 ELSE 3 END,
    checked_at DESC;
```

```sql
SELECT created_at, entity_type, action, message, error_detail
FROM activity_logs
WHERE status = 'failure'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

---

## 11. Filters (dashboard global)

Thêm Metabase dashboard filters:

| Filter | Column / field |
| ------ | -------------- |
| Date range | `growth_date`, `join_time`, `kpi_date` |
| Country | `country_target` |
| Vendor | `vendor_name` / `vendor_id` |
| X account | `x_account_handle` |
| Campaign | `campaign_id` |

---

## 12. Refresh & alerts

| Item | Khuyến nghị |
| ---- | ----------- |
| Cache | 15 phút cho growth; 1h cho intel |
| Pulse email | Purgatory count > 5 → email founder |
| Telegram | Agent 5 gửi 20:00 — dùng cùng SQL views (`v_daily_kpis_dashboard`) |

---

## 13. Metabase API (optional)

Tạo dashboard programmatically (Phase 8):

```bash
# Example — list databases
curl -s "$METABASE_URL/api/database" \
  -H "x-api-key: $METABASE_API_KEY"
```

Cards nên trỏ native query tới views ở trên — không duplicate business logic trong Metabase.

---

## 14. View reference (đầy đủ)

| View | Phase | Mục đích |
| ---- | ----- | -------- |
| `v_daily_growth` | 0 | Joins/ngày |
| `v_growth_overview` | 3 | KPI snapshot founder |
| `v_country_performance` | 0 | Performance theo country |
| `v_vendor_performance` | 0 | Performance theo vendor |
| `v_x_account_performance` | 3 | Join theo X account |
| `v_campaign_performance` | 3 | Cost per join |
| `v_content_performance` | 0+5 | Content + join rate + tier |
| `v_winning_content` | 5 | Winning hooks for repurpose |
| `v_content_status_summary` | 5 | Status pipeline counts |
| `v_content_leaderboard` | 3 | Top hook/hashtag/angle |
| `v_crm_stage_funnel` | 0 | Funnel + stage age |
| `v_crm_conversion` | 3 | Conversion % |
| `v_purgatory_dashboard` | 0+3 | Alerts kẹt |
| `v_apify_crawl_health` | 3 | Crawl runs |
| `v_country_intelligence_summary` | 3 | Daily intel |
| `v_system_health` | 0 | Service health |
| `v_daily_kpis_dashboard` | 3 | Rollup `daily_kpis` |

---

## 15. Acceptance checklist

- [ ] `views.sql` chạy không lỗi trên Supabase
- [ ] Metabase kết nối Supabase thành công
- [ ] 8 sections có ít nhất 1 card mỗi section
- [ ] Purgatory hiển thị đủ 6 alert types
- [ ] Không card nào trỏ Google Sheet
- [ ] Founder đọc spec này có thể tự tạo dashboard trong Metabase UI

---

*Phase 3 — spec only; Metabase instance do ops host. SQL views là contract giữa Supabase và Metabase.*

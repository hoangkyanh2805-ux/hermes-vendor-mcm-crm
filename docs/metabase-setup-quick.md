# Metabase — Setup nhanh (sau VNC install)

**URL:** https://agent.tiemhoatmon.com/metabase  
**Hoặc trực tiếp:** http://103.97.126.28:3000

---

## 1. Tạo admin (lần đầu)

- Email founder
- Password mạnh
- Tên org: `MCM Vendor`

---

## 2. Kết nối Supabase

**Admin → Databases → Add database → PostgreSQL**

| Field | Giá trị |
| ----- | ------- |
| Display name | `Supabase Hermes Growth` |
| Host | `aws-1-ap-southeast-1.pooler.supabase.com` |
| Port | `6543` |
| Database name | `postgres` |
| Username | `postgres.tpkuivbcaeenavwnjhit` |
| Password | *(Supabase DB password)* |
| SSL | Bật / Require |

**Schemas:** chỉ `public`

---

## 3. Dashboard founder

**New → Dashboard → 「MCM Growth OS — Founder」**

Thêm cards từ views (Browse data → hoặc SQL):

### Card nhanh — 4 số đầu

```sql
SELECT joins_today FROM v_growth_overview;
```

```sql
SELECT joins_7d FROM v_growth_overview;
```

```sql
SELECT top_country_30d FROM v_growth_overview;
```

```sql
SELECT top_x_account_30d FROM v_growth_overview;
```

Visualization: **Number** / **Scalar**

### Chart joins theo ngày

```sql
SELECT growth_date, telegram_joins
FROM v_daily_growth
ORDER BY growth_date;
```

Visualization: **Line chart**

### CRM funnel

```sql
SELECT * FROM v_crm_stage_funnel ORDER BY sort_order;
```

Visualization: **Bar chart**

### Winning content

```sql
SELECT * FROM v_winning_content LIMIT 10;
```

### Purgatory alerts

```sql
SELECT * FROM v_purgatory_dashboard;
```

---

## 4. 8 sections (đủ spec)

| # | Section | Views |
| - | ------- | ----- |
| 1 | Growth | `v_growth_overview`, `v_daily_growth` |
| 2 | Country | `v_country_performance` |
| 3 | Vendor | `v_vendor_performance` |
| 4 | Content | `v_content_performance`, `v_winning_content` |
| 5 | CRM | `v_crm_stage_funnel` |
| 6 | Purgatory | `v_purgatory_dashboard` |
| 7 | Apify | `v_apify_crawl_health` |
| 8 | Health | `v_system_health` |

Chi tiết: `config/metabase-dashboard-spec.md`

---

## 5. Verify

- [ ] Dashboard load không lỗi
- [ ] Cards có data (hoặc 0 nếu mới go-live)
- [ ] Không kết nối Google Sheet

---

*Bước tiếp theo sau Metabase: Twenty CRM live sync + Activepieces flows*

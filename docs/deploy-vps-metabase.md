# Deploy VPS — Hermes Webhook + Metabase

Hướng dẫn go-live: **Telegram `/start` tự động** + **Metabase founder dashboard**.

Project Supabase: `tpkuivbcaeenavwnjhit`  
Bot: `@hermes_vendor_mcm_crm_bot`

---

## Yêu cầu VPS

| Mục | Gợi ý |
| --- | ----- |
| OS | Ubuntu 22.04+ |
| RAM | 2 GB+ (Metabase + webhook) |
| Domain | Trỏ A record → IP VPS (HTTPS bắt buộc cho Telegram webhook) |
| Ports | 80, 443 mở |

---

## Phần A — Chuẩn bị server

```bash
ssh root@YOUR_VPS_IP

apt update && apt install -y git python3 python3-venv docker.io docker-compose-plugin caddy

# User vận hành
useradd -m -s /bin/bash hermes || true

# Clone repo
sudo -u hermes git clone https://github.com/hoangkyanh2805-ux/hermes-vendor-mcm-crm.git /opt/hermes-vendor-mcm-crm
cd /opt/hermes-vendor-mcm-crm

# Copy .env từ máy local (SCP) — KHÔNG commit
# scp .env hermes@YOUR_VPS:/opt/hermes-vendor-mcm-crm/.env
```

### `.env` bổ sung cho VPS

```env
APP_BASE_URL=https://YOUR_DOMAIN
HERMES_WEBHOOK_SECRET=<chạy: python scripts/set_telegram_webhook.py gen-secret>
WEBHOOK_PORT=8080
METABASE_PORT=3000
METABASE_URL=https://YOUR_DOMAIN/metabase
```

Giữ nguyên: `DATABASE_URL`, `TELEGRAM_*`, `SUPABASE_*`.

---

## Phần B — Hermes webhook (tự động `/start`)

### Cách 1: Docker (khuyên dùng)

```bash
cd /opt/hermes-vendor-mcm-crm
docker compose build hermes-webhook
docker compose up -d hermes-webhook
curl http://127.0.0.1:8080/health
```

### Cách 2: systemd (không Docker)

```bash
cd /opt/hermes-vendor-mcm-crm
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

sudo cp deploy/systemd/hermes-webhook.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-webhook
curl http://127.0.0.1:8080/health
```

### HTTPS reverse proxy (Caddy)

```bash
# Sửa YOUR_DOMAIN trong deploy/caddy/Caddyfile
sudo cp deploy/caddy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl https://YOUR_DOMAIN/health
```

### Đăng ký Telegram webhook

```bash
cd /opt/hermes-vendor-mcm-crm
.venv/bin/python scripts/set_telegram_webhook.py set
.venv/bin/python scripts/set_telegram_webhook.py info
```

`getWebhookInfo` phải show `url` = `https://YOUR_DOMAIN/webhook/telegram/...`

### Test live

1. Mở `https://t.me/hermes_vendor_mcm_crm_bot?start=src_xacc_uae_001_uae_goldhook_20260624`
2. Bấm **Start**
3. Kiểm tra:
   - Welcome message trong chat
   - Admin alert trong group `vendor_mcm_crm_bot`
   - Supabase → `telegram_joins` có row mới

```bash
.venv/bin/python scripts/sync_to_supabase.py health
```

---

## Phần C — Cron Agent 5 (cùng VPS)

```bash
sudo -u hermes crontab -e
```

```cron
*/30 * * * * cd /opt/hermes-vendor-mcm-crm && .venv/bin/python scripts/health_check.py --persist
0 20 * * *   cd /opt/hermes-vendor-mcm-crm && .venv/bin/python scripts/send_telegram_report.py founder-daily
0  9 * * 1   cd /opt/hermes-vendor-mcm-crm && .venv/bin/python scripts/send_telegram_report.py founder-daily --weekly
0  6 * * *   cd /opt/hermes-vendor-mcm-crm && .venv/bin/python scripts/run_apify_crawl.py run --country Canada --hashtag "#xauusd"
```

---

## Phần D — Metabase founder dashboard

### 1. Chạy Metabase

```bash
cd /opt/hermes-vendor-mcm-crm
docker compose up -d metabase
```

Truy cập: `http://YOUR_VPS_IP:3000` hoặc `https://YOUR_DOMAIN/metabase` (nếu Caddy strip prefix).

Lần đầu: tạo admin account founder.

### 2. Kết nối Supabase

Metabase → **Admin** → **Databases** → **Add database**

| Field | Giá trị |
| ----- | ------- |
| Database type | PostgreSQL |
| Host | `aws-1-ap-southeast-1.pooler.supabase.com` |
| Port | `6543` |
| Database name | `postgres` |
| Username | `postgres.tpkuivbcaeenavwnjhit` |
| Password | *(DB password Supabase)* |
| SSL | ON |

**Schemas:** `public` only.

### 3. Tạo dashboard

Theo `config/metabase-dashboard-spec.md`:

1. New dashboard: **「MCM Growth OS — Founder」**
2. Add cards từ views (SQL hoặc pick table):

| Section | View chính |
| ------- | ---------- |
| Growth | `v_growth_overview`, `v_daily_growth` |
| Country | `v_country_performance` |
| Vendor | `v_vendor_performance` |
| Content | `v_content_performance`, `v_winning_content` |
| CRM | `v_crm_stage_funnel` |
| Purgatory | `v_purgatory_dashboard` |
| Apify | `v_apify_crawl_health` |
| Health | `v_system_health` |

### 4. Card nhanh — Joins today

```sql
SELECT joins_today FROM v_growth_overview;
```

Visualization: **Number**.

### 5. Cập nhật `.env`

```env
METABASE_URL=https://YOUR_DOMAIN/metabase
```

---

## Troubleshooting

| Triệu chứng | Xử lý |
| ----------- | ----- |
| `/start` không phản hồi | `set_telegram_webhook.py info` — URL phải HTTPS |
| Webhook 403 | `HERMES_WEBHOOK_SECRET` khớp URL path |
| Metabase không connect | Dùng pooler port 6543, SSL on, user `postgres.tpkuivbcaeenavwnjhit` |
| View trống | Bình thường lúc đầu — chạy test join |
| Caddy 502 | `docker compose ps` — webhook container running? |

---

## Checklist go-live

- [ ] `https://YOUR_DOMAIN/health` → ok
- [ ] Telegram webhook registered
- [ ] `/start` deep link → welcome + Supabase row
- [ ] Metabase connected Supabase
- [ ] Dashboard 8 sections có cards
- [ ] Cron founder-daily 20:00

---

*Sau deploy: tick `docs/launch-checklist.md` Phase 1 + Phase 3 production items.*

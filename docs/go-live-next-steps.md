# Go-live — Bước tiếp theo (agent.tiemhoatmon.com)

Thứ tự thực hiện sau khi VPS + domain sẵn sàng.

---

## Trạng thái checklist

| # | Bước | Status |
| - | ---- | ------ |
| 0 | Supabase + `.env` | ✅ |
| 1 | Telegram bot + admin group | ✅ |
| 2 | **VPS install** (webhook + Caddy) | ⏳ **đang chờ VNC** |
| 3 | Telegram webhook live | ⏳ sau bước 2 |
| 4 | Metabase founder dashboard | ⏳ sau bước 2 |
| 5 | Twenty CRM live sync | ⏳ |
| 6 | Activepieces 6 flows | ⏳ |
| 7 | Cron Agent 5 (20:00 report) | ⏳ |

---

## Bước 2 — VPS (BẮT BUỘC trước)

VNC → clipboard → **1 lệnh:**

```bash
curl -fsSL https://raw.githubusercontent.com/hoangkyanh2805-ux/hermes-vendor-mcm-crm/master/deploy/remote-install.sh | bash
```

**Gõ tay nếu không paste:** xem [`deploy/VNC-INSTALL.md`](../deploy/VNC-INSTALL.md)

**Panel firewall:** mở TCP **443**, **2018**

**Verify:**

```bash
curl https://agent.tiemhoatmon.com/health
```

Kỳ vọng: `{"status":"ok",...}`

---

## Bước 3 — Webhook tự động (từ máy Windows)

Sau khi health OK:

```powershell
python scripts/poll_set_webhook.py --once
python scripts/poll_set_webhook.py
```

Hoặc:

```powershell
python scripts/set_telegram_webhook.py set
python scripts/set_telegram_webhook.py info
```

**Test bot:**

```
https://t.me/hermes_vendor_mcm_crm_bot?start=src_xacc_uae_001_uae_goldhook_20260624
```

---

## Bước 4 — Metabase

URL: https://agent.tiemhoatmon.com/metabase

Chi tiết: [`metabase-setup-quick.md`](metabase-setup-quick.md)

| Field | Giá trị |
| ----- | ------- |
| Host | `aws-1-ap-southeast-1.pooler.supabase.com` |
| Port | `6543` |
| User | `postgres.tpkuivbcaeenavwnjhit` |
| SSL | ON |

Dashboard: **「MCM Growth OS — Founder」** — 8 sections

---

## Bước 5 — Twenty CRM

1. Tạo workspace Twenty (cloud hoặc self-host)
2. Tạo 8 Opportunity stages khớp `config/twenty-pipeline.json`
3. `.env`: `TWENTY_API_URL`, `TWENTY_API_KEY`
4. Test:

```bash
python scripts/sync_to_twenty.py sync-lead --telegram-user-id 672890533 --live
```

---

## Bước 6 — Activepieces

1. Deploy Activepieces (cloud hoặc Docker)
2. Build 6 flows: `config/activepieces-flows-spec.md`
3. Copy webhook URLs → `.env` `ACTIVEPIECES_WEBHOOK_FLOW1`…`FLOW6`
4. Test: `python scripts/activepieces_webhook_test.py test`

---

## Bước 7 — Cron VPS

```cron
*/30 * * * *  cd /opt/hermes-vendor-mcm-crm && .venv/bin/python scripts/health_check.py --persist
0 20 * * *    cd /opt/hermes-vendor-mcm-crm && .venv/bin/python scripts/send_telegram_report.py founder-daily
0  9 * * 1    cd /opt/hermes-vendor-mcm-crm && .venv/bin/python scripts/send_telegram_report.py founder-daily --weekly
0  6 * * *    cd /opt/hermes-vendor-mcm-crm && .venv/bin/python scripts/run_apify_crawl.py run --country Canada --hashtag "#xauusd"
```

---

## Song song (không cần VPS)

- Đọc + setup **Twenty** account
- Đọc **Activepieces** flows spec
- Chuẩn bị **Apify** token khi cần crawl live

---

*Cập nhật: chờ VNC install hoàn tất bước 2*

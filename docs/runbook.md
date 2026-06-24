# Runbook — Vận hành hàng ngày

Thao tác thực tế cho team vận hành MCM Growth OS. Agent 5 bổ sung mục mới sau mỗi phase.

---

## Khởi động nhanh

```bash
cp .env.example .env          # điền secrets
pip install -r requirements.txt
python scripts/sync_to_supabase.py health
python scripts/sync_to_twenty.py health
```

---

## Phase 0 — Database

| Việc | Lệnh |
| ---- | ---- |
| Deploy schema | `psql $DATABASE_URL -f db/schema.sql` |
| Seed stages | `psql $DATABASE_URL -f db/seed_stages.sql` |
| Deploy views | `psql $DATABASE_URL -f db/views.sql` |
| Health | `python scripts/sync_to_supabase.py health` |

**Troubleshoot:** `DATABASE_URL` sai → kiểm tra Supabase → Settings → Database → connection string.

---

## Phase 1 — Telegram capture

| Việc | Lệnh |
| ---- | ---- |
| Test join (DB only) | `python scripts/sync_to_supabase.py test-join --payload "src_xacc_uae_001_uae_goldhook_20260624"` |
| Full capture | `python scripts/sync_to_supabase.py capture-start --user-id ID --username user --payload "src_..."` |
| Test welcome | `python scripts/send_telegram_report.py test-welcome --user-id ID` |

**Deep link format:**

```
https://t.me/BOT?start=src_{x_account}_{country}_{campaign}
```

**Troubleshoot:**

| Triệu chứng | Xử lý |
| ----------- | ----- |
| Admin không nhận báo | Kiểm tra `TELEGRAM_ADMIN_CHAT_ID`, bot đã vào group |
| `parse_status=invalid` | Campaign chưa có trong `campaigns` table |
| `unknown_source` | Thêm `x_accounts` record trước khi dùng deep link |
| DB ok, Telegram fail | Xem `activity_logs` action `send_welcome` / `admin_notify` |

---

## Phase 2 — Twenty CRM sync

| Việc | Lệnh |
| ---- | ---- |
| Health | `python scripts/sync_to_twenty.py health` |
| Dry-run sync | `python scripts/sync_to_twenty.py test-sync --dry-run` |
| Live sync 1 lead | `python scripts/sync_to_twenty.py sync-lead --telegram-user-id 999000001 --live` |
| Sync by lead UUID | `python scripts/sync_to_twenty.py sync-lead --lead-id <uuid>` |

**Trước khi sync live:**

1. Tạo Opportunity stages trong Twenty khớp `config/twenty-pipeline.json` → `twenty_stage_map`
2. Set `TWENTY_API_URL` + `TWENTY_API_KEY` trong `.env`

**Troubleshoot:**

| Triệu chứng | Xử lý |
| ----------- | ----- |
| Twenty 401 | API key hết hạn → Settings → APIs |
| Stage enum lỗi | Cập nhật `twenty_stage_map` theo enum workspace Twenty |
| Sync fail nhưng lead có trong Supabase | Bình thường — SoT là Supabase; xem `activity_logs` + `crm_stage_events.twenty_sync_error` |
| Lead không có trong Twenty | Chạy `sync-lead` thủ công hoặc chờ cron Agent 4 |

**Verify:**

```sql
SELECT * FROM crm_stage_events WHERE triggered_by = 'agent4' ORDER BY created_at DESC LIMIT 5;
SELECT raw_payload->>'twenty_person_id' FROM leads WHERE telegram_user_id = 999000001;
```

---

## Phase 3 — Metabase

| Việc | Lệnh / tài liệu |
| ---- | ---------------- |
| Deploy views | `psql $DATABASE_URL -f db/views.sql` |
| Đọc spec dashboard | `config/metabase-dashboard-spec.md` |
| Smoke test views | SQL trong sop-ops Phase 3 |
| Kết nối Metabase | Admin → PostgreSQL → Supabase SSL |

**8 sections:** Growth, Country, Vendor, Content, CRM Funnel, Purgatory, Apify Health, System Health.

**Troubleshoot:**

| Triệu chứng | Xử lý |
| ----------- | ----- |
| Metabase không connect | Bật SSL; dùng connection pooler port 6543 |
| View không thấy | Re-run `views.sql`; refresh schema Metabase |
| Card trống | Bình thường nếu chưa có data — test với `test-join` Phase 1 |
| Cost/join null | Set `budget_usd` trên `campaigns` |

---

## Phase 4 — Apify / Country Intelligence

| Việc | Lệnh |
| ---- | ---- |
| Health | `python scripts/run_apify_crawl.py health` |
| Test offline (Canada) | `python scripts/normalize_apify_dataset.py --sample --dry-run` |
| Full pipeline + DB | `python scripts/run_apify_crawl.py test-canada --report` |
| Live crawl | `python scripts/run_apify_crawl.py run --country Canada --hashtag "#xauusd"` |
| Admin report | `python scripts/send_telegram_report.py country-report --dry-run` |

**Env:** `APIFY_API_TOKEN`, `APIFY_X_ACTOR_ID=EvFXOhwR6wsOWmdSK`, `DATABASE_URL`

**Troubleshoot:**

| Triệu chứng | Xử lý |
| ----------- | ----- |
| No APIFY token | Dùng `test-canada` / `--sample` cho dev |
| Actor input lỗi | Chỉnh `build_actor_input()` trong `run_apify_crawl.py` theo schema Actor |
| 0 hooks | Kiểm tra posts noise/promo — sample có 16 hooks |
| Telegram fail | DB vẫn OK; xem `activity_logs` |

---

## Phase 5 — Content Performance

| Việc | Lệnh |
| ---- | ---- |
| Insert posted content | `python scripts/sync_to_supabase.py content-insert --content-id ID ...` |
| Update metrics | `python scripts/sync_to_supabase.py content-metrics --content-id ID --clicks N` |
| Mark winning | `python scripts/sync_to_supabase.py content-mark-winning --content-id ID` |
| Full acceptance | `python scripts/sync_to_supabase.py content-test` |
| Join attribution | Deep link kết thúc bằng `_{content_id}` e.g. `..._goldhook_20260624_hook001` |

**Verify:**

```sql
SELECT * FROM v_content_performance WHERE content_id = 'hook001';
SELECT * FROM v_winning_content;
```

---

## Phase 6 — Plane vendor board

| Việc | Lệnh |
| ---- | ---- |
| Health | `python scripts/create_plane_task.py health` |
| Dry-run task | `create --country UAE --angle breakout --dry-run` |
| Local test | `python scripts/create_plane_task.py test` |
| Từ Apify High | `from-apify --local-only` |
| Từ winning content | `from-winning --content-id hook001 --local-only` |
| Sync status | `sync-status --vendor-task-id UUID` |

**Spec:** `config/plane-board-spec.md` — SOP hàng ngày team Tuấn.

**Setup:** `PLANE_API_URL`, `PLANE_API_KEY`, `PLANE_WORKSPACE_ID`, `PLANE_PROJECT_ID`

---

## Phase 7 — Activepieces

| Việc | Lệnh |
| ---- | ---- |
| Đọc spec | `config/activepieces-flows-spec.md` |
| Health | `python scripts/activepieces_webhook_test.py health` |
| Sample payload | `sample-payload --flow 1` (1–6) |
| Dry-run send | `send --flow 1 --dry-run` |
| Test failure log | `log-failure --flow 3 --message "test"` |
| Acceptance | `python scripts/activepieces_webhook_test.py test` |

**Setup:** Publish 6 flows trên Activepieces → copy webhook URLs vào `.env` `ACTIVEPIECES_WEBHOOK_FLOW1`…`FLOW6`

**Supabase:** Database Webhooks → Activepieces URL cho `telegram_joins`, `crm_stage_events`, `apify_posts`, `daily_kpis`

---

## Phase 8 — Agent 5 Monitor / Operating Rhythm

| Việc | Lệnh |
| ---- | ---- |
| Full health JSON | `python scripts/health_check.py` |
| Persist logs | `python scripts/health_check.py --persist` |
| Founder metrics | `python scripts/health_check.py founder-data` |
| Weekly review data | `python scripts/health_check.py weekly-review` |
| Verify SOP bundle | `python scripts/health_check.py bundle` |
| Preview 8PM report | `python scripts/send_telegram_report.py founder-daily --dry-run` |
| Send 8PM report | `python scripts/send_telegram_report.py founder-daily` |
| Weekly review Telegram | `python scripts/send_telegram_report.py founder-daily --weekly` |

**Cron (VPS / Hermes):**

```cron
*/30 * * * *  python scripts/health_check.py --persist
0 20 * * *    python scripts/send_telegram_report.py founder-daily
0 9 * * 1     python scripts/send_telegram_report.py founder-daily --weekly
```

**Env:** `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`  
**Optional:** `GITHUB_MONITOR_ENABLED=auto|false`, `psutil` for VPS CPU/MEM

**Troubleshoot:**

| Triệu chứng | Xử lý |
| ----------- | ----- |
| Report trống / N/A | Chưa có data — chạy Phase 1–7 test flows |
| `metrics_error` | Kiểm tra `DATABASE_URL`, re-run `db/views.sql` |
| Service FAILED trong report | Chạy health từng script (`sync_to_supabase.py health`, etc.) |
| GitHub `documented pending` | Bình thường nếu không có `.git` local |
| Telegram không gửi | `TELEGRAM_ADMIN_CHAT_ID`, dùng `--dry-run` trước |

**Verify:**

```sql
SELECT service_name, status, message, checked_at
FROM system_health_logs ORDER BY checked_at DESC LIMIT 20;
```

---

## Phase 9 — E2E launch test

| Việc | Lệnh |
| ---- | ---- |
| Full E2E | `python scripts/e2e_launch_test.py` |
| Save report | `python scripts/e2e_launch_test.py --report e2e-report.json` |
| Live Twenty step | `python scripts/e2e_launch_test.py --live-twenty` |
| Bundle verify | `python scripts/health_check.py bundle` |

**12 steps:** foundation → capture → content → CRM → Apify → vendor → automation → views → bundle → founder report → activity_logs → stack health.

**Pass:** exit code 0 + `summary.launch_ready: true`

**Troubleshoot:**

| Triệu chứng | Xử lý |
| ----------- | ----- |
| Step 1 fail | `DATABASE_URL`, `docker compose up`, re-run schema |
| Step 8 views missing | `psql $DATABASE_URL -f db/views.sql` |
| Step 11 failures | Xem `activity_logs` — loại trừ intentional test |
| Step 4 CRM | Bình thường dry-run; dùng `--live-twenty` khi Twenty ready |

---

## Phase 10 — SOP bundle

| Việc | Path |
| ---- | ---- |
| Setup guide | `README.md` |
| AI rules | `CLAUDE.md` |
| Case study map | `docs/case-study-mapping.md` |
| Bundle inventory | `docs/bundle-manifest.md` (25/25) |

```bash
python scripts/health_check.py bundle
python scripts/e2e_launch_test.py
```

---

## Production VPS — agent.tiemhoatmon.com (123host)

**Chi tiết VNC / paste lệnh:** [deploy/VNC-INSTALL.md](../deploy/VNC-INSTALL.md)

| Mục | Giá trị |
| --- | ------- |
| IP | `103.97.126.28` |
| SSH | `ssh -p 2018 root@103.97.126.28` |
| Domain | `https://agent.tiemhoatmon.com` |
| Install 1-liner (VNC clipboard) | `curl -fsSL https://raw.githubusercontent.com/hoangkyanh2805-ux/hermes-vendor-mcm-crm/master/deploy/remote-install.sh \| bash` |

**Sau install:** Metabase → Section [deploy-vps-metabase.md](deploy-vps-metabase.md) Phần D.

---

## Agent 5 — Sau mỗi phase (packaging)

1. Chạy acceptance test của phase
2. Cập nhật `docs/bundle-manifest.md`
3. Cập nhật `docs/sop-ops.md` → status Complete
4. Bổ sung mục tương ứng trong runbook này
5. Tick `docs/launch-checklist.md`
6. Commit: `done: phaseN ...`

---

## Liên hệ tài liệu

- SOP chi tiết: [sop-ops.md](sop-ops.md)
- Master plan: [master-plan.md](master-plan.md)
- Bundle: [bundle-manifest.md](bundle-manifest.md)
- Launch: [launch-checklist.md](launch-checklist.md)
- Rollback: [rollback-plan.md](rollback-plan.md)

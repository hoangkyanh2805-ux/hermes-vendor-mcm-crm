# Launch Checklist — MVP Go-Live

Agent 5 tick từng mục khi phase tương ứng SHIP xong.

---

## Foundation

- [x] `.env` không commit (`.gitignore`)
- [x] ADR 001–005 có trong `docs/adr/`
- [ ] Supabase schema deployed production
- [ ] `sync_to_supabase.py health` → healthy

## Phase 1 — Telegram

- [x] `agent1-capture.yaml` trong bundle
- [ ] Telegram bot online production
- [ ] `/start` với payload hợp lệ → `telegram_joins`
- [ ] `/start` không payload → `unknown`
- [ ] Admin nhận báo join

## Phase 2 — Twenty CRM

- [x] `twenty-pipeline.json` + `sync_to_twenty.py` trong bundle
- [x] `agent4-twenty-crm-sync.yaml` thay EspoCRM
- [ ] Twenty stages khớp `twenty_stage_map`
- [ ] 1 lead test sync Supabase → Twenty live
- [ ] Stage change Supabase → cập nhật Twenty
- [ ] EspoCRM **không** bắt buộc cho core flow

## Phase 3 — Metabase

- [x] `metabase-dashboard-spec.md` trong bundle
- [x] `views.sql` có 15 views dashboard
- [ ] Metabase kết nối Supabase production
- [ ] 8 sections có cards trên Metabase UI
- [ ] Founder xem được KPI (có thể empty data lúc đầu)
- [ ] Không card nào dùng Google Sheet

## Phase 4 — Apify

- [x] `apify-xauusd-crawl.json` + scripts trong bundle
- [x] `agent3-daily-loop.yaml` với cron
- [x] 3 prompts classify/hook/report
- [ ] `APIFY_API_TOKEN` set production
- [ ] `test-canada` insert DB thành công
- [ ] Live crawl Canada + #xauusd (optional MVP)
- [ ] Admin nhận country report

## Phase 5 — Content performance

- [x] `content_performance` tracker + CLI
- [x] `v_content_performance`, `v_winning_content` views
- [x] Join attribution via content_id in deep link
- [x] Metabase Section 4 updated
- [ ] `content-test` pass trên production DB

## Phase 6 — Plane

- [x] `plane-board-spec.md` + `create_plane_task.py`
- [ ] Plane project + 7 states configured
- [ ] `create --dry-run` OK
- [ ] `test` hoặc live create → `vendor_tasks.plane_task_id`
- [ ] `from-apify` tạo task từ High potential post

## Phase 7 — Activepieces

- [x] `activepieces-flows-spec.md` + `activepieces-flows.json`
- [x] `activepieces_webhook_test.py`
- [ ] Activepieces instance deployed
- [ ] 6 flows published trong UI
- [ ] `send --flow 1` live test OK
- [ ] `activity_logs` ghi failure path

## Phase 8 — Agent 5

- [x] `health_check.py` JSON output (all services)
- [x] `health_check.py --persist` → `system_health_logs`
- [x] `founder-daily` báo cáo 20:00 (7 sections)
- [x] `founder-daily --weekly` weekly review
- [x] Failed services hiển thị rõ trong report
- [x] `prompts/report-founder.txt` template
- [x] `skills/agent5-monitor.yaml` phase8
- [x] Runbook + bundle manifest cập nhật Phase 8

## Phase 9 — E2E

- [x] `scripts/e2e_launch_test.py` — 12-step simulated journey
- [x] E2E covers: capture → content → CRM → Apify → Plane → automation → views → monitor
- [x] `activity_logs` critical failure check (24h, excludes test noise)
- [x] `rollback-plan.md` reviewed (Phase 8–9 sections)
- [ ] **Production:** chạy `e2e_launch_test.py` trên production DB trước go-live
- [ ] **Production:** không critical error thực tế trong `activity_logs` 24h

## Phase 10 — Bundle

- [x] `README.md` setup instructions
- [x] `docs/case-study-mapping.md`
- [x] `CLAUDE.md` v2
- [x] `skills/agent2-onboard.yaml` (5/5 skills)
- [x] Bundle manifest 100% ✅

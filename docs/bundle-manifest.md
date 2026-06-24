# Bundle Manifest — MCM Vendor SOP Package

Agent 5 cập nhật file này sau **mỗi phase SHIP**.  
**Phase 10:** gói hoàn chỉnh — có thể tái sử dụng cho ngành khác.

---

## Trạng thái đóng gói

| # | Thành phần | Path | Phase | Status |
| - | ---------- | ---- | ----- | ------ |
| 1 | CLAUDE.md v2 | `CLAUDE.md` | 10 | ✅ |
| 2 | Skill Agent 1 — Capture | `skills/agent1-capture.yaml` | 1 | ✅ |
| 3 | Skill Agent 2 — Onboard | `skills/agent2-onboard.yaml` | 10 | ✅ (MVP documented) |
| 4 | Skill Agent 3 — Daily loop | `skills/agent3-daily-loop.yaml` | 4 | ✅ |
| 5 | Skill Agent 4 — Twenty CRM | `skills/agent4-twenty-crm-sync.yaml` | 2 | ✅ |
| 6 | Skill Agent 5 — Monitor | `skills/agent5-monitor.yaml` | 8 | ✅ |
| 7 | Legacy EspoCRM (ref only) | `skills/agent4-crm-sync.yaml` | 2 | ✅ deprecated |
| 8 | Prompt library | `prompts/*.txt` | 4, 8 | ✅ (4 prompts) |
| 9 | Supabase schema | `db/schema.sql`, `seed_stages.sql`, `views.sql` | 0–3 | ✅ |
| 10 | Twenty pipeline | `config/twenty-pipeline.json` | 2 | ✅ |
| 11 | Metabase dashboard spec | `config/metabase-dashboard-spec.md` | 3 | ✅ |
| 12 | Plane board spec | `config/plane-board-spec.md`, `plane-board.json` | 6 | ✅ |
| 13 | Activepieces flows | `config/activepieces-flows-spec.md`, `activepieces-flows.json` | 7 | ✅ |
| 14 | Apify crawl config | `config/apify-xauusd-crawl.json` | 4 | ✅ |
| 15 | Scripts | `scripts/*.py` | 0–9 | ✅ |
| 16 | SOP / OPS | `docs/sop-ops.md` | 0–10 | ✅ |
| 17 | Runbook | `docs/runbook.md` | 0–10 | ✅ |
| 18 | Launch checklist | `docs/launch-checklist.md` | 9 | ✅ |
| 19 | Rollback plan | `docs/rollback-plan.md` | 8–9 | ✅ |
| 20 | Case study mapping | `docs/case-study-mapping.md` | 10 | ✅ |
| 21 | README setup | `README.md` | 10 | ✅ |
| 22 | ADRs | `docs/adr/001–005` | 0 | ✅ |
| 23 | Master plan | `docs/master-plan.md` | — | ✅ |
| 24 | Env template | `.env.example` | 0 | ✅ |
| 25 | E2E launch test | `scripts/e2e_launch_test.py` | 9 | ✅ |

**Bundle complete:** 25/25 ✅

---

## Scripts trong bundle

| Script | Phase | Mô tả |
| ------ | ----- | ----- |
| `sync_to_supabase.py` | 0–1 | Supabase upsert, capture /start |
| `send_telegram_report.py` | 1, 8 | Welcome, admin alert, founder-daily |
| `sync_to_twenty.py` | 2 | Supabase → Twenty CRM |
| `run_apify_crawl.py` | 4 | Apify actor crawl |
| `normalize_apify_dataset.py` | 4 | Normalize + classify + intel |
| `health_check.py` | 8 | System health, founder-data, bundle verify |
| `create_plane_task.py` | 6 | Plane vendor/content tasks |
| `activepieces_webhook_test.py` | 7 | Webhook test + automation logs |
| `e2e_launch_test.py` | 9 | Full lead journey launch test |

---

## Quy tắc thích ứng ngành mới (Phase 10)

**Đổi:** landing copy, D1–D7 scripts, qualification, countries, hashtags, stage labels  
**Giữ:** 5 skills, Supabase SoT, CRM, dashboard spec, workboard, automation bridge, Agent 5 rhythm

Chi tiết: [`case-study-mapping.md`](case-study-mapping.md)

---

## Verify

```bash
python scripts/health_check.py bundle
python scripts/e2e_launch_test.py
```

---

*Cập nhật lần cuối: Phase 10 SHIP — SOP bundle hoàn chỉnh*

# Rollback Plan

Agent 5 cập nhật khi thêm dependency mới.

---

## Nguyên tắc

- **Supabase** luôn là nguồn sự thật — rollback CRM/dashboard không xóa lead data
- Rollback **từng layer**, không rollback toàn stack một lúc trừ khi critical

---

## Phase 0 — Supabase

| Sự cố | Rollback |
| ----- | -------- |
| Schema migration lỗi | Restore Supabase backup snapshot |
| Trigger gây lỗi insert | `DROP TRIGGER` tạm thời, fix SQL, redeploy |

## Phase 1 — Telegram

| Sự cố | Rollback |
| ----- | -------- |
| Bot gửi spam welcome | Tắt webhook Hermes; dùng `--no-welcome` trong script |
| Capture ghi sai attribution | Sửa `leads`/`telegram_joins` trực tiếp trên Supabase; không dùng Sheet |

## Phase 2 — Twenty CRM

| Sự cố | Rollback |
| ----- | -------- |
| Twenty API down | **Tiếp tục vận hành** — capture vẫn vào Supabase; tắt cron Agent 4 |
| Sync stage sai | Sửa stage trên Supabase; re-sync `sync-lead --lead-id` |
| Muốn tắt Twenty hoàn toàn | Stop `sync_to_twenty.py` cron; EspoCRM legacy **không** tự bật lại |

## Phase 7 — Activepieces

| Sự cố | Rollback |
| ----- | -------- |
| Flow loop / duplicate alerts | Tắt flow trên Activepieces; vận hành manual scripts |
| Webhook flood | Disable Supabase webhook; filter `is_duplicate` |
| Wrong stage update | Sửa trên Supabase; Twenty re-sync |

## Phase 6 — Plane

| Sự cố | Rollback |
| ----- | -------- |
| Task trùng trên Plane | Dùng `vendor_tasks` Supabase làm index; archive trên Plane |
| Sync status sai | Map lại `plane_state_id` trong `plane-board.json` |
| Plane down | Vận hành qua `vendor_tasks` + runbook; tạo task local `--local-only` |

## Phase 5 — Content performance

| Sự cố | Rollback |
| ----- | -------- |
| join_rate sai | Sửa `clicks`/`telegram_joins` trực tiếp; `join_rate` tự tính lại |
| Winning mark nhầm | `content-metrics --status posted` + sửa `content_assets.status` |

## Phase 4 — Apify

| Sự cố | Rollback |
| ----- | -------- |
| Crawl spam/noise | Tăng ngưỡng classify; filter `category=noise` trong reports |
| Apify quota hết | Dừng cron 06:00; dùng sample mode; không xóa `apify_posts` cũ |
| Actor schema đổi | Pin actor version; sửa `build_actor_input()` |

## Phase 8 — Agent 5 Monitor / Operating Rhythm

| Sự cố | Rollback |
| ----- | -------- |
| Founder report sai số | Dùng `founder-data` so sánh với Metabase views; sửa data trên Supabase |
| Health poll spam `system_health_logs` | Tắt cron `--persist`; retention policy trên table |
| False FAILED trong report | Service chưa config → `unknown` bình thường; set env hoặc `GITHUB_MONITOR_ENABLED=false` |
| Telegram 8PM flood | Tắt cron `founder-daily`; dùng `--dry-run` để debug |
| Weekly review sai | Chạy `weekly-review` JSON; verify `v_crm_stage_funnel` |

**Không rollback:** `health_check.py` chỉ đọc — không ghi trừ `--persist` và Telegram send.

---

## Phase 9 — E2E launch test

| Sự cố | Rollback |
| ----- | -------- |
| E2E fail step 2–3 | Test data trong DB — xóa test leads/joins nếu cần (`TEST_TELEGRAM_USER_ID` range) |
| E2E tạo noise `activity_logs` | Filter `actor=e2e` hoặc test users 99900* |
| False positive step 11 | Review query excludes intentional test failures |
| Production E2E fail | **Không go-live** — fix failing step per runbook Phase tương ứng |

---

## Phase 3+ (dự kiến)

| Layer | Rollback |
| ----- | -------- |
| Metabase | Dashboard chỉ đọc views — tắt Metabase không ảnh hưởng capture |
| Apify | Dừng cron crawl; data cũ giữ trong `apify_posts` |
| Plane | Dừng tạo task; `vendor_tasks` local vẫn ok |
| Activepieces | Tắt flows; manual notify qua `send_telegram_report.py` |

---

## Emergency contacts / ownership

| Layer | Owner | Ghi chú |
| ----- | ----- | ------- |
| Supabase | Founder / Dev | Backup daily |
| Telegram bot | Ops | Token rotate via BotFather |
| Twenty | Ops | Self-hosted hoặc cloud |
| VPS Hermes | Ops | `docker compose` / systemd |

---

*Cập nhật: Phase 9–10 — E2E + bundle complete*

# Plane Vendor / Content Board Spec
# MCM Vendor — Hermes XAUUSD Growth OS v2 — Phase 6

**Tool:** [Plane](https://plane.so) — workboard cho team Tuấn (vendor/content)  
**Mirror table:** `vendor_tasks` (Supabase) — Plane task ID lưu tại `plane_task_id`

---

## 1. Mục tiêu

Cho team Tuấn một board rõ ràng: từ Apify intel / winning content → task → đăng bài → track → winning.

Supabase là source of truth; Plane là UI vận hành.

---

## 2. Board columns

| Column (Plane) | `vendor_tasks.status` | Khi nào dùng |
| -------------- | --------------------- | ------------ |
| Backlog | `backlog` | Task mới từ Apify, founder, hoặc repurpose |
| Ready to Post | `ready_to_post` | Hook/angle đã chốt, chờ assign |
| Assigned | `assigned` | Vendor đã nhận, có deadline |
| Posted | `posted` | Đã đăng X — chờ metrics |
| Need Fix | `need_fix` | Metrics thấp hoặc founder feedback |
| Winning Content | `winning` | join_rate cao — repurpose |
| Archived | `archived` | Hết hạn / không dùng nữa |

**Overdue:** `vendor_tasks.status` có thể set `overdue` khi `deadline < NOW()` và chưa posted (hiện trong `v_purgatory_dashboard`).

Config mapping: `config/plane-board.json`

---

## 3. Task template

### Title

```
[Country] [Hashtag] [Angle]
```

Ví dụ: `[UAE] #xauusd Breakout long`

### Description (HTML trong Plane)

```html
<h3>MCM Vendor Content Task</h3>
<ul>
  <li><b>Country:</b> UAE</li>
  <li><b>Hashtag:</b> #xauusd</li>
  <li><b>Angle:</b> breakout</li>
  <li><b>Hook:</b> Gold breakout above 2350...</li>
  <li><b>Source post URL:</b> https://x.com/...</li>
  <li><b>Target account group:</b> xacc_uae_001</li>
  <li><b>Vendor:</b> Demo Vendor</li>
  <li><b>Expected output:</b> 1 X post + BioLink update</li>
  <li><b>Deadline:</b> 2026-06-26</li>
  <li><b>CTA:</b> Join Telegram for daily gold setups</li>
  <li><b>BioLink/Telegram:</b> https://t.me/bot?start=src_xacc_uae_001_uae_campaign_content</li>
  <li><b>Acceptance criteria:</b> Posted on X, link in bio, join tracked in Supabase</li>
</ul>
```

Script `create_plane_task.py` build description tự động từ các field trên.

---

## 4. Nguồn tạo task

| Nguồn | Command / flow |
| ----- | -------------- |
| High potential Apify post | `create_plane_task.py from-apify --post-id UUID` |
| Country opportunity report | `from-intel --country Canada` |
| Manual founder request | `create --country UAE --hashtag "#xauusd" ...` |
| Winning content repurpose | `from-winning --content-id hook001` |
| Vendor overdue recovery | `from-vendor-task --task-id UUID` (re-open Need Fix) |

---

## 5. Setup Plane

### Env

```env
PLANE_API_URL=https://api.plane.so
PLANE_API_KEY=plane_api_...
PLANE_WORKSPACE_ID=my-team          # workspace slug (URL segment)
PLANE_PROJECT_ID=<project-uuid>
```

Optional state IDs (map column → Plane state):

```env
PLANE_STATE_BACKLOG=
PLANE_STATE_READY_TO_POST=
PLANE_STATE_ASSIGNED=
```

### Tạo project & states

1. Plane → Workspace → New Project **「MCM Vendor Content」**
2. Settings → States — tạo 7 states khớp columns trên
3. Copy state UUIDs vào `config/plane-board.json` hoặc `.env`
4. API token: Workspace Settings → API Tokens

### List states (debug)

```bash
python scripts/create_plane_task.py list-states
```

---

## 6. Scripts

```bash
python scripts/create_plane_task.py health
python scripts/create_plane_task.py create \
  --country UAE --hashtag "#xauusd" --angle breakout \
  --hook "Gold breakout 2350" --source-url "https://x.com/..." \
  --x-account xacc_uae_001 --deadline 2026-06-26 \
  --dry-run

python scripts/create_plane_task.py create ...   # live (+ ghi vendor_tasks)
python scripts/create_plane_task.py from-apify --limit 1
python scripts/create_plane_task.py from-winning --content-id hook001
python scripts/create_plane_task.py sync-status --vendor-task-id UUID
```

---

## 7. SOP hàng ngày — Team Tuấn

### Sáng (sau crawl 06:00)

1. Mở Plane board **Backlog** + **Ready to Post**
2. Founder/Agent đã push task từ Apify intel — ưu tiên `High` potential
3. Kéo task → **Assigned**, set deadline trong Plane

### Trước khi đăng

1. Copy **Hook** + **BioLink/Telegram** từ task description
2. Đăng X từ account trong **Target account group**
3. Kéo task → **Posted**
4. Chạy (hoặc automation Phase 7): `content-insert` với `content_id` khớp deep link

### Cuối ngày

1. Founder report 21:00 — xem country/vendor performance
2. Task metrics thấp → **Need Fix**
3. Task join_rate cao → **Winning Content** → tạo repurpose task tuần sau

### Thứ 2 hàng tuần

1. Review **Winning Content** — clone 3 hooks sang country mới
2. Archive task > 30 ngày không dùng

---

## 8. Sync ngược Plane → Supabase

`sync-status` (Phase 6 stub, mở rộng Phase 7 Activepieces):

1. GET work-item từ Plane API
2. Map `state_id` → `vendor_tasks.status`
3. Update `vendor_tasks` + `activity_logs`

Webhook Plane (Phase 7): issue updated → sync Supabase.

---

## 9. Metabase / Purgatory

- `v_vendor_performance.overdue_tasks`
- `v_purgatory_dashboard` alert_type = `vendor_overdue`

---

## 10. Acceptance

- [ ] `create_plane_task.py create --dry-run` in payload hợp lệ
- [ ] Live create ghi `vendor_tasks.plane_task_id`
- [ ] `from-apify` tạo task từ `lead_potential=High`
- [ ] `sync-status` documented / stub works
- [ ] Team Tuấn đọc Section 7 có thể vận hành board

---

*Phase 6 — Plane spec + script; full webhook sync in Phase 7 Activepieces.*

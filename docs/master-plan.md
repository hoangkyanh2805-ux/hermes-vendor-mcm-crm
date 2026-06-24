# Master Plan — MCM Vendor Hermes XAUUSD Growth OS v2

Lifecycle: **DEFINE → PLAN → BUILD → VERIFY → REVIEW → SHIP**  
Framework: [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)

> **Quy tắc Agent 5:** Sau mỗi phase SHIP, Agent 5 cập nhật bundle manifest, SOP, runbook, launch checklist — không đợi Phase 10.

---

## Bản đồ phase

| Phase | Module | Deliverable chính | Agent | Bundle (Agent 5) |
| ----- | ------ | ----------------- | ----- | ---------------- |
| 0 | Source of truth | `db/schema.sql`, views, seed | — | ✓ schema + sync script |
| 1 | Capture | `agent1-capture.yaml`, Telegram attribution | Agent 1 | ✓ skill + runbook capture |
| 2 | CRM pipeline | `agent4-twenty-crm-sync.yaml`, `sync_to_twenty.py` | Agent 4 | ✓ Twenty config + sync |
| 3 | Dashboard | `metabase-dashboard-spec.md`, views | — | ✓ dashboard spec |
| 4 | Intelligence | Apify crawl, country reports | Agent 3 | ✓ crawl config + prompts |
| 5 | Content perf | `content_performance` tracker | — | ✓ metrics views |
| 6 | Vendor board | Plane spec + `create_plane_task.py` | — | ✓ board spec |
| 7 | Automation | Activepieces flows spec | — | ✓ flow spec |
| 8 | Operating rhythm | `agent5-monitor.yaml`, `health_check.py` | Agent 5 | ✓ daily report + health |
| 9 | Launch | E2E test, launch checklist pass | Agent 5 | ✓ full checklist |
| 10 | SOP bundle | README, case-study-mapping, package | Agent 5 | ✓ **bundle hoàn chỉnh** |

---

## Agent 5 — Đóng gói incremental

```
Phase SHIP → verify acceptance → bundle-manifest → sop-ops → runbook → launch-checklist → commit
```

| Tài liệu | Vai trò |
| -------- | ------- |
| [bundle-manifest.md](bundle-manifest.md) | Danh mục file trong gói SOP bán lại |
| [sop-ops.md](sop-ops.md) | SOP từng phase (SPEC/PLAN/BUILD/TEST/REVIEW/SHIP) |
| [runbook.md](runbook.md) | Thao tác hàng ngày, lệnh, troubleshoot |
| [launch-checklist.md](launch-checklist.md) | Checklist trước go-live |
| [rollback-plan.md](rollback-plan.md) | Quay lui khi lỗi production |

---

## Trạng thái hiện tại

| Phase | Status |
| ----- | ------ |
| 0 | ✅ Complete |
| 1 | ✅ Complete |
| 2 | 🔄 In progress (code done, cần test Twenty live) |
| 3 | ✅ Complete (spec + views) |
| 4 | ✅ Complete |
| 5 | ✅ Complete |
| 6 | ✅ Complete |
| 7 | ✅ Complete (spec — flows build trên Activepieces UI) |
| 8 | ✅ Complete (health + founder report + weekly review) |
| 9 | ✅ Complete (E2E launch test script + checklist) |
| 10 | ✅ Complete (SOP bundle — README, CLAUDE, case-study-mapping) |

---

## Commit convention

```
feat: [phase-name] [short-description]
done: [phase-name] [completed-scope]
test: [phase-name] [result]
```

---

## Kiến trúc (nhắc nhanh)

```
X traffic → BioLink/UTM → Telegram → Supabase (SoT)
  → Twenty CRM → Metabase → Plane → Activepieces → Hermes rhythm (Agent 5)
```

1 Hermes = 5 skills. Không Agent 6. EspoCRM = legacy only.

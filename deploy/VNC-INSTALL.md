# VNC Console — Cài Hermes trên 123host (noVNC)

**Lưu bước này** khi SSH port 2018 bị chặn hoặc không paste được lệnh bằng Ctrl+V.

---

## Thông tin VPS production

| Mục | Giá trị |
| --- | ------- |
| IP | `103.97.126.28` |
| SSH port | `2018` |
| Domain | `agent.tiemhoatmon.com` |
| Console | 123host → noVNC (Proxmox) |
| Login | `root` + password VPS |
| Code path | `/opt/hermes-vendor-mcm-crm` |

---

## Bước 1 — Đăng nhập VNC

1. Panel 123host → **Console** / noVNC
2. Gõ tay: `root` → Enter
3. Gõ password VPS → Enter (không hiện ký tự — bình thường)

---

## Bước 2 — Paste lệnh (noVNC không dùng Ctrl+V)

**Cách 1 — Clipboard noVNC (khuyên dùng):**

1. Bấm **tab xám bên trái** màn hình đen (hoặc icon Clipboard trên thanh noVNC)
2. Dán lệnh vào ô **Clipboard**
3. Bấm **Paste** / **Send**
4. Enter trong terminal

**Cách 2 — Phím tắt:** `Ctrl + Alt + Shift` → mở menu clipboard (tùy trình duyệt)

**Cách 3 — SSH từ máy Windows** (paste bình thường):

```powershell
ssh -p 2018 root@103.97.126.28
```

*(Cần mở TCP 2018 + 443 trong firewall panel nếu timeout.)*

---

## Bước 3 — Lệnh cài đầy đủ (1 dòng)

```bash
curl -fsSL https://raw.githubusercontent.com/hoangkyanh2805-ux/hermes-vendor-mcm-crm/master/deploy/remote-install.sh | bash
```

Chờ 3–5 phút → thấy `DONE`.

---

## Bước 4 — Nếu không paste được (gõ từng dòng)

```bash
cd /opt/hermes-vendor-mcm-crm
```

```bash
bash deploy/vps-bootstrap.sh
```

Nếu chưa có thư mục:

```bash
git clone https://github.com/hoangkyanh2805-ux/hermes-vendor-mcm-crm.git /opt/hermes-vendor-mcm-crm
```

*(Cần copy `.env` từ máy local lên `/opt/hermes-vendor-mcm-crm/.env` nếu lần đầu.)*

---

## Bước 5 — Verify sau cài

```bash
curl -sf https://agent.tiemhoatmon.com/health
systemctl status hermes-webhook
docker ps
```

| URL | Kỳ vọng |
| --- | ------- |
| https://agent.tiemhoatmon.com/health | `{"status":"ok"}` |
| https://agent.tiemhoatmon.com/metabase | Metabase setup |
| Bot test | https://t.me/hermes_vendor_mcm_crm_bot?start=src_xacc_uae_001_uae_goldhook_20260624 |

---

## Firewall panel (123host)

Mở nếu HTTPS/SSH fail:

- **TCP 443** — Telegram webhook HTTPS
- **TCP 2018** — SSH admin
- **TCP 80** — Caddy HTTP challenge

---

## Bước tiếp theo (sau VNC install)

1. **Metabase** — https://agent.tiemhoatmon.com/metabase → add Supabase PostgreSQL
2. **Test bot** — deep link `/start` → welcome + admin alert
3. **Cron** — `docs/deploy-vps-metabase.md` phần cron Agent 5

---

*Cập nhật: go-live agent.tiemhoatmon.com — VNC 123host noVNC*

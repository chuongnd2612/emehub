# Thông tin project

**Sản phẩm:** EmeHub
**Đội:** `CLGT-EAM` · **Thành viên:** `Nguyễn Đình Chương - Đào Văn Linh - Đồng Huỳnh Giao`

---

## 1. Link truy cập hệ thống

Cả suite nằm sau một địa chỉ duy nhất. Bắt đầu từ EmeHub.

| Ứng dụng | Đường dẫn |
|---|---|
| **EmeHub** — hub chứa landing page, navigate tới agent | `https://hub.chuongnd.click` |
| **Q-Agent** — agent cho QC/QA | `https://hub.chuongnd.click/qagent/` |

Đăng nhập một lần ở EmeHub là dùng được cả hai, không phải đăng nhập lại khi chuyển sang agent.
Agent thêm vào sau — D-Agent cho DEV, B-Agent cho BA — sẽ chiếm một path segment mới trên cùng
địa chỉ này.

---

## 2. Tài khoản demo

| Role | Username | Password |
|---|---|---|
| Admin | `hub.admin@emesoft.net` | `010203x@X` |
| Member | `demo.user1@emesoft.net` | `Demo@123` |

Cả hai tài khoản dùng chung một đường đăng nhập ở EmeHub và đều mở được Q-Agent mà không phải
đăng nhập lại.

---

## 3. Source code

| Repository | Ứng dụng | Trạng thái |
|---|---|---|
| [`chuongnd2612/emehub`](https://github.com/chuongnd2612/emehub) | **EmeHub** — hub: identity, credential, project, knowledge base | Public · branch `master` |
| [`chuongnd2612/q-agent`](https://github.com/chuongnd2612/q-agent) | **Q-Agent** — agent cho QC/QA | Public · branch `master` |

Hai repository tách nhau và tích hợp qua HTTP, không phải monorepo — contract giữa chúng là một
tài liệu thật, `docs/INTEGRATION.md` trong repo hub.

Điểm vào khi đọc code:

| Muốn xem | Ở đâu |
|---|---|
| Bộ tài liệu dự thi | `emehub/docs/product/` |
| Quyết định kiến trúc kèm lý do | `emehub/docs/adr/` |
| Contract giữa hub và agent | `emehub/docs/INTEGRATION.md` |
| Backend hub (FastAPI) | `emehub/api/app/` |
| Frontend hub (React) | `emehub/app/src/` |
| Skill của Q-Agent | `q-agent/skills/` |
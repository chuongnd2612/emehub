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

Dùng tài khoản nào cho việc gì:

| Xem thứ gì | Đăng nhập bằng |
|---|---|
| Integrations, Claude credential dùng chung, User Management, audit log | **Admin** — những màn này yêu cầu role `admin` |
| Project riêng của một thành viên, clone project từ shared namespace, credential Claude cá nhân | **Member** — đúng góc nhìn của một QC/QA |

Cả hai tài khoản dùng chung một đường đăng nhập ở EmeHub và đều mở được Q-Agent mà không phải
đăng nhập lại.
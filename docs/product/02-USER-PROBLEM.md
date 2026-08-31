# 1.2 User & Problem Analysis

---

## User Persona

### Persona 1 — Trang, QC/QA Engineer *(primary)*

| | |
|---|---|
| **Bối cảnh** | 3 năm kinh nghiệm manual test, biết đọc TypeScript, viết Playwright ở mức cơ bản |
| **Công cụ** | Azure DevOps (work item + test plan), Chrome DevTools, Excel, thỉnh thoảng ChatGPT |
| **Khối lượng** | 8–15 ticket/sprint, mỗi ticket 3–12 test case |
| **Mục tiêu** | Không để lọt case; automation không đỏ vì lý do vặt |
| **Bực mình vì** | Gõ lại cùng một nội dung ba lần; sửa selector sau mỗi lần UI đổi |
| **Không muốn** | Một cái nút "AI generate" mà output phải viết lại từ đầu |

### Persona 2 — Hùng, Tech Lead / Admin *(secondary)*

| | |
|---|---|
| **Bối cảnh** | Quản lý 2 team, chịu trách nhiệm về access và chi phí |
| **Mục tiêu** | Một chỗ để cấp và thu hồi quyền; nhìn được chi phí Claude theo người |
| **Bực mình vì** | PAT nằm trong `.env` trên máy từng người; người nghỉ việc phải đi thu hồi thủ công |
| **Rào cản chấp nhận** | Tool nào yêu cầu đẩy source code ra dịch vụ ngoài đều bị loại |

### Persona 3 — Nam, Developer *(future)*

Chưa phải user hôm nay. Được đưa vào phân tích vì hub phải phục vụ được agent của Nam mà không
đổi schema — đây là ràng buộc thiết kế, không phải scope của bản dự thi.

---

## Current User Journey — Trang, một ticket

| # | Bước | Công cụ | Thời gian | Vấn đề |
|---|---|---|---|---|
| 1 | Đọc work item, mở AC | Azure DevOps | 10' | AC viết thiếu, phải hỏi BA |
| 2 | Viết test case ra Excel/notepad | Excel | 45' | Không có template thống nhất |
| 3 | Nhập từng case vào Azure DevOps | Azure DevOps | 30' | Gõ lại nội dung bước 2, form chậm |
| 4 | Link case vào work item | Azure DevOps | 10' | Thủ công, dễ sót |
| 5 | Viết spec Playwright | VS Code | 90' | Phải tự dò selector trên DOM |
| 6 | Chạy, sửa selector, chạy lại | Terminal | 60' | Vòng lặp không đoán trước được |
| 7 | Chụp evidence, đính kèm | Chrome + ADO | 20' | Thủ công từng ảnh |
| 8 | Comment kết quả về ticket | Azure DevOps | 10' | Gõ lại lần thứ ba |

Tổng: **~4.5 giờ/ticket**, trong đó phần cần chuyên môn thật (bước 1 và phần suy nghĩ của bước 2)
chiếm khoảng 25%.

> Con số baseline ở bảng trên là **ước lượng nội bộ** của đội trên các ticket web UI cỡ vừa
> (3–12 test case), không phải kết quả đo có kiểm soát. Phương pháp đo và số đã đo nằm ở
> [09-SUCCESS-METRICS.md](09-SUCCESS-METRICS.md).

### Nhánh "nhờ AI" hiện tại

Trang mở chat AI, dán mô tả ticket, xin test case. Kết quả: danh sách chung chung, không biết
route thật, không biết selector thật, không truy vết được tới AC. Xin luôn spec Playwright thì
được code trông hợp lý, chạy fail ở dòng đầu tiên vì selector là đoán. Chi phí sửa ≈ chi phí tự
viết, nên nhánh này bị bỏ.

---

## Pain Points

| # | Pain | Nguyên nhân gốc | Đo bằng |
|---|---|---|---|
| P1 | Gõ lại cùng một nội dung 3 lần | Không có đường dẫn dữ liệu giữa requirement → test case → spec → comment | Thời gian bước 2,3,8 |
| P2 | Automation đỏ sau mỗi lần UI đổi | Selector không ổn định, không có page object dùng chung | Số spec phải sửa/sprint |
| P3 | AI sinh code không chạy được | Model không có grounding về DOM/route thật của project | Tỉ lệ spec pass ở lần chạy đầu |
| P4 | Chất lượng output phụ thuộc kỹ năng viết prompt | Không có prompt/skill chuẩn hoá đi kèm sản phẩm | Độ lệch kết quả giữa các thành viên |
| P5 | Credential phân mảnh, không audit được | Mỗi tool tự giữ user/PAT/Claude credential | Số nơi phải thu hồi khi có người rời team |
| P6 | Claude account dùng chung bị nghẽn, không biết ai tiêu bao nhiêu | Không có usage attribution per-user | Rate limit hit / tháng |

---

## Jobs To Be Done

| JTBD | Phát biểu |
|---|---|
| **JTBD-1** | Khi nhận một ticket, tôi muốn có bộ test case bám đúng acceptance criteria, để không phải tự bảo đảm coverage bằng trí nhớ |
| **JTBD-2** | Khi test case đã duyệt, tôi muốn có spec automation **chạy được ngay**, để không tốn vòng debug selector |
| **JTBD-3** | Khi UI đổi, tôi muốn chỉ sửa một chỗ, để không phải mở lại từng spec |
| **JTBD-4** | Khi báo cáo kết quả, tôi muốn evidence và comment tự về ticket, để PM nhìn ticket là đủ |
| **JTBD-5** | *(Admin)* Khi có người vào/rời team, tôi muốn cấp và thu hồi ở một chỗ, để không bỏ sót quyền |
| **JTBD-6** | *(Admin)* Khi cả đội dùng AI, tôi muốn biết chi phí theo người và theo project, để kiểm soát ngân sách |

---

## Current-State Flow

```
Requirement (ADO work item)
   │  đọc thủ công
   ▼
Test case trong Excel ──gõ lại──► Test case trong ADO ──link tay──► Work item
   │  đọc lại
   ▼
Spec Playwright viết tay ──chạy──► FAIL (selector đoán) ──sửa tay──► chạy lại ──►…
   │
   ▼
Evidence chụp tay ──đính kèm tay──► Comment gõ tay ──► Work item

Credential:  PAT trong .env máy Trang · Claude account chung, không attribution
             Cấu hình project khai riêng ở từng tool
```

Đặc điểm: **không có đường dẫn dữ liệu nào giữa các bước** — mọi chuyển tiếp là con người copy.

---

## Future-State Flow

```
                        ┌──────────────────── EmeHub ────────────────────┐
                        │ user · session · role · 2FA                    │
                        │ Claude credential (own → shared → none)        │
                        │ provider connection (PAT encrypted, proxy)     │
                        │ project · environment · test account · repo    │
                        │ KNOWLEDGE BASE (build từ source thật)          │
                        │ audit log append-only                          │
                        └───────────────┬────────────────────────────────┘
                                        │ HTTP + hub-issued JWT (audience-scoped)
                        ┌───────────────▼───────────────┐
                        │            Q-Agent            │
                        │  ticket → test case → spec    │
                        │  → execution → evidence       │
                        └───────────────┬───────────────┘
                                        │ ghi ngược: selector verified-at-runtime
                                        └────────► Knowledge Base

  Agent tương lai (D-Agent, B-Agent) gắn vào cùng contract, chiếm một path segment mới.
```

Luồng của Trang sau khi đổi:

| # | Bước | Ai làm | Thời gian |
|---|---|---|---|
| 1 | Sync ticket, tạo Run | Trang | 1' |
| 2 | AI phân tích AC, sinh test case có truy vết | Q-Agent | ~3' |
| 3 | **Review Center — duyệt/sửa/từ chối từng case** | **Trang** | 10–15' |
| 4 | Tạo case trên ADO và link vào work item | Q-Agent | ~1' |
| 5 | Live-harness: chạy thật trên app, emit spec | Q-Agent | 5–15' |
| 6 | Execution + evidence | Q-Agent / Local Agent | 5' |
| 7 | Comment kết quả về ticket (preview trước khi gửi) | Trang duyệt, Q-Agent gửi | 2' |

Con người còn đúng ba điểm quyết định: duyệt test case, duyệt bước push lên provider, duyệt
comment. Ba chỗ đó là chỗ cần phán đoán; phần còn lại là chỗ máy làm tốt hơn.

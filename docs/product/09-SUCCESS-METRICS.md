# 4.2 Success Metrics & Business Impact

Nguyên tắc: mỗi metric phải nói được **đo ở đâu trong hệ thống**. Metric không có nguồn dữ liệu
là metric không đo được, và không được đưa vào bảng.

Ô `[…]` là số đội phải đo trước khi công bố ra ngoài. Để trống có chủ đích còn hơn điền số ước lượng.

---

## Product Success Metrics

Ba câu hỏi quyết định sản phẩm này có thành công hay không:

| # | Câu hỏi | Metric | Nguồn dữ liệu | Ngưỡng đạt |
|---|---|---|---|---|
| PS1 | Output có dùng được ngay không? | **First-run green rate** — % spec chạy green ngay lần đầu, không heal | Bảng execution của run | ≥ 80% ở mode `live-harness` |
| PS2 | Người có tin đủ để duyệt nhanh không? | **Review acceptance rate** — % case approve mà không sửa | Review Center | ≥ 70% |
| PS3 | Nền tảng có thật sự dùng lại được không? | **Số lần khai lại cấu hình khi thêm agent** | Đếm thủ công khi onboard agent mới | = 0 |

PS1 là metric trung tâm, vì nó chính là phát biểu sản phẩm: *spec sinh từ DOM thật chạy được ngay.*
PS3 là metric trung tâm của **hub**, và chỉ đo được khi agent thứ ba onboard.

---

## User Metrics

| # | Metric | Định nghĩa | Nguồn |
|---|---|---|---|
| U1 | Weekly active user | User có ≥1 run/tuần | `sessions` + run log |
| U2 | Run / user / sprint | Số ticket một QC/QA chạy qua pipeline | Run log |
| U3 | Tỉ lệ hoàn tất pipeline | % run đi hết tới bước Publish | Trạng thái run |
| U4 | Điểm dừng phổ biến nhất | Bước mà run bị bỏ dở nhiều nhất | Trạng thái run |
| U5 | Thời gian ở Review Center | Phút/ticket người thực sự ngồi duyệt | Timestamp Review Center |
| U6 | Tỉ lệ dùng shared credential | % user chạy bằng credential chung | `claude_credentials.mode` |
| U7 | Tỉ lệ clone project | % project tạo bằng clone thay vì build lại | `projects` |

U4 là metric chẩn đoán quan trọng nhất: run bị bỏ ở đâu thì chỗ đó là chỗ sản phẩm đang tệ nhất.

---

## AI Metrics

Định nghĩa đầy đủ ở [07-AI-EVALUATION.md](07-AI-EVALUATION.md); bảng này là phần theo dõi liên tục.

| # | Metric | Nguồn | Ghi chú |
|---|---|---|---|
| A1 | **AC coverage** — % AC có ≥1 case map tới | Mapping AC → case | Đo trước khi người duyệt |
| A2 | **Grounding pass rate** — % spec qua placeholder gate lần đầu | Placeholder gate | Rơi xuống là dấu hiệu KB `stale` |
| A3 | **First-run green rate** | Execution | = PS1 |
| A4 | **Heal convergence** — % spec đỏ xanh lại trong ≤3 lần | Execution | Chỉ áp dụng mode `blind` |
| A5 | **Failure class distribution** | `execution-analyzer` | `product_defect` tăng là tín hiệu về sản phẩm được test, không phải về AI |
| A6 | **Token / run**, **cost / run** | `claude_usage` | Attribute theo owner |
| A7 | **Tỉ lệ run bị bounded chặn** (cost ceiling / turn cap / timeout) | Run log | Cao = ngân sách sai hoặc scope quá lớn |
| A8 | **Số entry verified-at-runtime ghi ngược KB** | `project_knowledge` | Đo mức KB giàu lên theo thời gian |

A8 đáng theo dõi vì nó là vòng phản hồi duy nhất khiến hệ thống **tốt lên theo thời gian** mà không
cần ai sửa prompt.

---

## Productivity Impact

Bốn nguồn hiệu quả, xếp theo mức độ chắc chắn:

| # | Nguồn | Cơ chế | Chắc chắn tới đâu |
|---|---|---|---|
| 1 | **Xoá bước gõ lại** | Requirement → case → ADO → spec → comment đi bằng dữ liệu, không bằng copy tay | Cao — cơ học, không phụ thuộc chất lượng AI |
| 2 | **Đầu vào tốt hơn nên output dùng được** | AI làm việc trên KB của repo thật | Cao — placeholder gate và first-run green rate đo được |
| 3 | **Bảo trì automation chuyển sang máy** | Page object dùng lại + heal có grounding | Trung bình — phụ thuộc mức độ UI đổi |
| 4 | **Khép vòng về ticket** | Evidence và comment tự về work item; PM nhìn ticket là đủ | Cao |

Hiệu quả **không** nằm ở chỗ "AI gõ nhanh hơn người". Nó nằm ở chỗ output không phải làm lại.

---

## Time Saved

| Công việc | Trước *(ước lượng nội bộ, ticket web UI 3–12 case)* | Sau | Người còn làm gì |
|---|---|---|---|
| Viết test case | ~45' | ~3' AI + `[…]` người duyệt | Duyệt ở Review Center |
| Nhập case vào Azure DevOps + link | ~40' | ~1' | Chọn local mode hay write thật |
| Viết spec Playwright | ~90' | `[…]` live-harness | — |
| Chạy + sửa selector | ~60' | `[…]` | Xác nhận kết quả |
| Thu evidence + comment | ~30' | ~2' | Duyệt comment preview |
| **Tổng** | **~4.5 giờ** | **`[đo M8 wall-clock + M9 người-phút]`** | 3 gate |

Ngoài vòng ticket:

| Việc | Trước | Sau |
|---|---|---|
| Build knowledge cho member thứ hai | ~20' build | Clone project từ shared namespace |
| Onboard một agent mới vào hệ thống | Khai lại user, PAT, credential, project | Đọc contract, dùng lại nền tảng |
| Thu hồi quyền khi có người rời team | Nhiều nơi, dễ sót | Revoke session ở hub = logout mọi agent |

> Cột "Trước" là **ước lượng nội bộ** của đội, không phải kết quả đo có kiểm soát. Cột "Sau" phải
> điền bằng số đo thật trước khi dùng ngoài đội.

---

## Cost Reduction

| Trục | Cách tính | Nguồn |
|---|---|---|
| **Chi phí LLM / ticket** | Tổng cost của mọi call trong một run | `claude_usage`, hiển thị ở màn Execution |
| **Giờ công tiết kiệm / ticket** | (giờ trước − người-phút sau) × chi phí giờ công | Đo M9 |
| **ROI / ticket** | Giờ công tiết kiệm − chi phí LLM | Hai dòng trên |
| **Chi phí rate limit** | Số lần chạm limit của Claude account chung | `claude_usage` roll-up % session/weekly limit |

Hai cơ chế kiểm soát chi phí đã có sẵn, không phải làm thêm:

1. **Attribution per-user.** Mọi call ghi token + cost theo owner, roll up thành % session limit và
   weekly limit, hiển thị trên chip credential. Người dùng thấy mình đang tiêu bao nhiêu **trước
   khi** chạm giới hạn.
2. **Bounded run.** Cost ceiling + turn cap + wall-clock timeout cho mọi mode. Một run hỏng không
   thể tiêu tiền vô hạn.

---

## Quality Improvement

| # | Metric | Vì sao đo | Nguồn |
|---|---|---|---|
| Q1 | **AC coverage** | Case bỏ sót AC là lỗi coverage rõ ràng nhất | Mapping AC → case |
| Q2 | **Số defect phát hiện được trước release** | Giá trị thật của QA | Azure DevOps |
| Q3 | **Tỉ lệ `product_defect` trong failure class** | Test tìm ra bug thật, không chỉ test chính nó | `execution-analyzer` |
| Q4 | **Số spec phải sửa tay / sprint** | Đo trực tiếp chi phí bảo trì automation | Git log của repo test |
| Q5 | **Độ lệch kết quả giữa các thành viên** | Skill chuẩn hoá có thật sự làm đầu ra đồng đều không | So sánh output cùng ticket |
| Q6 | **Tỉ lệ flaky** | `flaky` trong failure class | `execution-analyzer` |

Q5 là metric của việc **chuẩn hoá prompt**: trước đây chất lượng phụ thuộc kỹ năng viết prompt của
từng người; với 15 skill đi kèm sản phẩm, cùng một ticket thì ai chạy cũng phải ra kết quả tương
đương. Độ lệch giảm là bằng chứng.

---

## Adoption Metrics

| Giai đoạn | Metric | Ngưỡng |
|---|---|---|
| **Pilot** | Số QC/QA chạy ≥3 ticket qua pipeline | `[…]` người |
| **Pilot** | Số project có KB `indexed` | `[…]` |
| **Mở rộng** | % ticket của sprint đi qua pipeline | `[…]` % |
| **Mở rộng** | % user dùng credential riêng thay vì shared | Tăng dần |
| **Trưởng thành** | Số agent tiêu thụ hub | 1 → 2 → 3 |
| **Trưởng thành** | Số bảng identity/credential còn tồn tại ngoài hub | → 0 |
| **Giữ chân** | % user tuần trước còn dùng tuần này | `[…]` % |
| **Tín hiệu tiêu cực** | % run bị bỏ dở, và bỏ ở bước nào | Giảm dần |

Hai metric cuối của mục "Trưởng thành" là metric của **hub**, không phải của agent — và chúng là
cách duy nhất để nói hub đã thành công. Một hub mà agent vẫn giữ bản sao user và credential thì
chưa phải source of truth, dù màn hình có đẹp tới đâu.

# 5.1 Demo Script

**Thời lượng:** 8 phút · **Đội:** CLGT-EAM · **URL:** `https://hub.chuongnd.click`

---

## Chuẩn bị trước khi quay

| # | Việc | Vì sao |
|---|---|---|
| 1 | Knowledge base của repo demo ở trạng thái **`indexed`** | Build mất tới ~20', không quay được |
| 2 | Ticket demo đã sync sẵn, có AC rõ ràng, 4–6 case | Đủ để thấy mapping AC → case, không dài |
| 3 | Chrome đã đăng nhập app đích, Local Agent đã pair và `start` | Live-harness cần browser authenticated |
| 4 | Claude credential ở trạng thái `Personal`, chip xanh | Tránh chết giữa demo |
| 5 | Một run **đã chạy xong** để dành, cùng ticket | Dự phòng nếu live-harness chậm — cắt sang run này |
| 6 | Tab mở sẵn: hub Overview · Q-Agent Tickets · Azure DevOps work item | Không tìm tab trên sóng |
| 7 | Zoom 110–125%, dark mode, accent EMESOFT Red | Chữ đọc được trên video |

---

## 1. Problem — 0:00–0:50

**Trên màn hình:** một work item Azure DevOps thật, cuộn qua phần acceptance criteria.

> "Đây là một ticket bình thường. Để test nó, QC/QA của chúng tôi phải gõ lại cùng một nội dung
> ba lần: một lần thành test case, một lần nhập vào Azure DevOps, một lần nữa thành script
> Playwright. Trung bình khoảng bốn tiếng rưỡi cho một ticket, và phần thực sự cần chuyên môn —
> case đã đủ chưa, rủi ro nằm ở đâu — chỉ chiếm chừng một phần tư."

**Chuyển tiếp — nêu luôn lý do cách làm hiển nhiên không chạy:**

> "Nhờ AI viết thẳng thì không dùng được. Model đoán selector từ ngữ cảnh nó nhìn thấy, sinh ra
> code trông hợp lý và fail ở dòng đầu tiên. Sửa nó tốn bằng tự viết."

---

## 2. Target User — 0:50–1:20

**Trên màn hình:** slide một dòng, hoặc cứ để nguyên work item.

> "Người dùng chính là QC/QA engineer — biết đọc code, viết Playwright ở mức cơ bản, chạy 8 đến
> 15 ticket mỗi sprint. Người dùng thứ hai là tech lead: người chịu trách nhiệm về quyền truy cập
> và chi phí, và hiện đang có PAT Azure DevOps nằm rải trong file `.env` trên máy từng người."

---

## 3. Product Introduction — 1:20–2:20

**Trên màn hình:** EmeHub Overview sau khi đăng nhập.

> "EmeHub là nơi khai báo một lần mọi thứ mà công cụ AI nội bộ dùng chung: người dùng, credential
> Claude, kết nối Azure DevOps, project, repository — và knowledge base về mã nguồn."

**Thao tác nhanh, không dừng lâu:**

1. **Integrations** — chỉ vào connection Azure DevOps: *"PAT dán một lần ở đây. Nó không bao giờ
   rời khỏi hub — API chỉ trả về `hasPat: true`."*
2. **Claude Settings** — chỉ vào chip credential: *"Credential riêng của tôi, hoặc credential
   chung của workspace, đổi qua lại bằng một toggle. Mỗi lần gọi Claude được ghi token và chi phí
   theo từng người."*
3. **Project → tab Knowledge** — trạng thái `indexed`: *"Đây là chỗ quan trọng nhất. Hub clone
   repository và cho Claude đọc toàn bộ mã nguồn, rút ra route thật, selector thật, page object,
   luồng đăng nhập. Build một lần, mọi agent cùng dùng."*
4. **Overview → card Q-Agent → Launch** — vào thẳng Q-Agent, không đăng nhập lần hai.

> "Đăng nhập một lần. Và thu hồi phiên ở hub là thiết bị đó bị đăng xuất khỏi mọi agent."

---

## 4. Golden User Journey — 2:20–4:30

**Trên màn hình:** Q-Agent, màn Tickets.

| Thời điểm | Thao tác | Lời thoại |
|---|---|---|
| 2:20 | Chọn ticket → **Create run** | "Từ đây là một Run. Trạng thái của Run chính là bước hiện tại." |
| 2:35 | Bước 1 chạy, chỉ vào cột **mapping AC → case** | "AI đọc acceptance criteria và sinh test case. Mỗi case chỉ rõ nó cover AC nào — nên chỗ hở nhìn thấy được, không phải đoán." |
| 3:00 | Mở **Review Center**, sửa một case, reject một case, đổi một case sang `Manual` | "Đây là gate bắt buộc. Case sinh ra ở trạng thái `pending`; chỉ case đã duyệt mới đi tiếp. Case tôi đánh dấu `Manual` sẽ không bao giờ được đem sinh script." |
| 3:40 | Bước **Link**, chỉ vào toggle local mode | "Đẩy case lên Azure DevOps. Có chế độ chạy thử: ghi local, không đụng vào provider." |
| 4:00 | Mở Azure DevOps ở tab khác, cho thấy case đã nằm trong work item | "Case đã ở đúng chỗ, đã link vào work item gốc." |

---

## 5. AI "Magic Moment" — 4:30–6:00

**Đây là phần quan trọng nhất của demo. Chậm lại.**

**Trên màn hình:** bấm **Automation**, mode `live-harness`. Chia màn hình: Q-Agent bên trái,
Chrome mà agent đang điều khiển bên phải.

> "Đây là chỗ khác biệt. Q-Agent **không sinh script ngay.**"

**Trong lúc browser chạy — thuyết minh theo thứ tự:**

> "Nó mở một Chrome đã đăng nhập sẵn và tự đi hết các bước của test case **trên ứng dụng thật**.
> Với mỗi phần tử, nó đọc cây accessibility để lấy selector ổn định nhất **thực sự tồn tại trên
> DOM** — ưu tiên `data-testid`, rồi ARIA role kèm tên, rồi label, cuối cùng mới tới CSS. Không
> `:nth-child`, không class trần."

> "Và nó **không verify bằng toạ độ.** Click theo toạ độ thì trúng bất kỳ thứ gì nằm ở điểm đó —
> thường là một thẻ `<a>` bên trong. Còn script thì sẽ click **chính selector được ghi lại**, mà
> tâm của selector đó có thể là một container không xử lý click. Nên mỗi thao tác được thực hiện
> trực tiếp trên đúng selector sắp được ghi, rồi kiểm tra hiệu ứng thật — URL có đổi không."

> "Thiếu dữ liệu test thì nó tự tạo qua giao diện, và ghi luôn phần chuẩn bị đó vào script để lần
> sau tự đứng được."

**Khi spec hiện ra — mở file, chỉ vào một selector:**

> "**Chạy hết và pass rồi mới sinh script** — dựng từ đúng những gì vừa chạy được. Selector này
> không phải suy đoán; nó vừa được bấm cách đây ba mươi giây."

**Chỉ vào placeholder gate:**

> "Và trước khi chạy, script còn qua một cửa kiểm tra: selector bịa, `TODO` bỏ trống, URL
> placeholder đều bị chặn với lý do rõ ràng — thay vì fail lặng lẽ lúc chạy rồi bị đọc nhầm thành
> lỗi sản phẩm."

---

## 6. Result — 6:00–7:00

**Trên màn hình:** Execution → Evidence → Publish.

| Thời điểm | Thao tác | Lời thoại |
|---|---|---|
| 6:00 | **Execution**, log chạy trực tiếp | "Script chạy xanh ngay lần đầu, không cần vòng sửa." |
| 6:15 | Chỉ vào failure class *(dùng run dự phòng có một ca đỏ)* | "Khi có ca đỏ, hệ thống phân loại: lỗi script, lỗi sản phẩm, flaky, môi trường hay timeout. Lỗi script thì tự sửa, tối đa ba lần. **Lỗi sản phẩm thì không sửa** — đó là kết quả đúng." |
| 6:30 | **Evidence** — screenshot có chú thích, video, trace | "Bằng chứng thu tự động." |
| 6:45 | **Publish** — mở preview comment, bấm gửi, chuyển sang tab Azure DevOps | "Comment được xem trước rồi mới gửi. Đây là gate thứ ba." |

**Trên work item:** cuộn cho thấy test case đã link, kết quả chạy và evidence.

> "Vòng khép lại tại chính ticket. PM nhìn ticket là đủ."

---

## 7. Impact — 7:00–7:40

**Trên màn hình:** một slide bảng, hoặc màn Execution có hiển thị chi phí.

> "Ba điều thay đổi."

| | |
|---|---|
| **Thời gian** | "Phần gõ lại chuyển từ giờ sang phút. Con người còn đúng ba điểm quyết định: duyệt test case, duyệt bước đẩy lên provider, duyệt comment." |
| **Chất lượng** | "Script sinh từ DOM thật nên chạy được ngay. Page object dùng lại giữa các ticket — UI đổi thì sửa một chỗ, đây là chỗ automation truyền thống tốn công nhất." |
| **Chuẩn hoá và kiểm soát** | "Mười lăm skill đi kèm sản phẩm nên không ai phải viết prompt — cùng một ticket thì ai chạy cũng ra kết quả tương đương. Chi phí Claude hiển thị theo từng run, ghi theo từng người. PAT không rời khỏi hub." |

*(Nếu đã có số đo M8/M9, đọc số ở đây. Nếu chưa, không đọc số nào.)*

---

## 8. Closing — 7:40–8:00

**Trên màn hình:** quay lại EmeHub Overview.

> "Hôm nay có hai ứng dụng chạy trên nền tảng này: hub và Q-Agent cho QC/QA. Agent tiếp theo —
> cho DEV, cho BA — gắn vào bằng **cùng một contract**, chiếm một path segment mới trên cùng địa
> chỉ, và **không phải dựng lại** identity, credential hay knowledge base. Đó là thứ chúng tôi xây
> hub để đổi lấy."

> "Nói thẳng một điều: hai agent chưa chuyển hẳn sang dùng hub cho mọi thứ — hôm nay Q-Agent mới
> dùng identity từ hub. Đó là việc tiếp theo, và là lý do phần nền tảng được làm trước."

---

## Phương án dự phòng

| Sự cố | Xử lý |
|---|---|
| Live-harness chạy chậm quá 90 giây | Cắt sang run đã chuẩn bị sẵn: *"đây là kết quả của đúng bước này"* |
| Chip credential đỏ | Đổi sang shared credential — chính là demo cho tính năng đó |
| Azure DevOps chậm | Dùng local mode ở bước Link, giải thích rằng đó là chế độ dry-run có sẵn |
| Không mở được app đích | Chuyển sang mode `blind` và nói rõ đây là fallback theo thiết kế |
| Knowledge base `stale` | Không build trên sóng. Chuyển sang project đã `indexed` |

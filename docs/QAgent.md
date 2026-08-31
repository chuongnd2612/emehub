# Q-Agent

## 1. Giới thiệu về ứng dụng

**Q-Agent** là ứng dụng web nội bộ giúp đội QC/QA **chuyển ticket thành công việc kiểm thử hoàn chỉnh**
bằng AI agent (Claude Code CLI) — test case đã duyệt, script Playwright đã chạy, bằng chứng đã thu,
kết quả đã comment về ticket.

Chọn ticket từ Azure DevOps → tạo một **Run** → AI phân tích yêu cầu, sinh test case, chờ QC/QA duyệt,
rồi tự dựng và chạy automation trên ứng dụng thật, thu bằng chứng và trả kết quả về ticket.

**Các màn hình chính:**

| Màn hình | Dùng để |
|---|---|
| **Dashboard** | Điểm vào, tình trạng các run đang chạy |
| **Projects / Project Details** | Cấu hình project, repository, test account, **Project Knowledge** |
| **Tickets** | Đồng bộ và chọn ticket từ provider |
| **Runs / Run Detail** | Danh sách run và màn hình theo dõi từng bước của pipeline |
| **Review Center** | Duyệt test case do AI sinh — bắt buộc, không bỏ qua được |
| **Local Agent** | Ghép nối máy tester để chạy test |
| **Reports** | Báo cáo kết quả kiểm thử |
| **Settings** | Kết nối provider, credential AI, mục tiêu thực thi, ngân sách |

**Pipeline 7 bước.** Việc chọn ticket xảy ra trước; mọi thứ sau đó thuộc về một **Run**, và trạng thái
của Run chính là bước hiện tại:

| # | Bước | Việc xảy ra |
|---|---|---|
| 1 | **Analyze & Generate** | AI phân tích yêu cầu, sinh test case theo định dạng Azure DevOps, có truy vết tới từng acceptance criteria |
| 2 | **Review** | QC/QA duyệt, sửa hoặc từ chối từng case |
| 3 | **Link** | Tạo case đã duyệt trên provider và gắn vào work item gốc |
| 4 | **Automation** | Sinh spec Playwright |
| 5 | **Execution** | Chạy spec, tự sửa khi fail |
| 6 | **Evidence** | Thu ảnh màn hình, video, trace, console, network |
| 7 | **Publish** | Comment kết quả về ticket, chuyển trạng thái ticket nếu muốn |

Run có thể **hủy, chạy lại hoặc xoá** ở bất kỳ bước nào.

**Hai chế độ sinh automation:**

| Chế độ | Cách làm | Chọn khi |
|---|---|---|
| **Live-authoring** *(khuyến nghị)* | AI mở browser đã đăng nhập, tự đi hết test case trên app thật, ghi lại selector thật, **pass rồi mới sinh spec** | Mặc định — spec chạy xanh ngay, không cần vòng sửa |
| **Blind** | Sinh spec từ knowledge base, fail thì tự sửa (heal) | Khi không thể mở browser tới app đó |

---

## 2. Hướng dẫn sử dụng

### Bước 0 — Chuẩn bị một lần

| # | Việc cần làm |
|---|---|
| 1 | Đăng nhập bằng tài khoản admin (tài khoản đầu tiên được tạo sẵn khi khởi động) |
| 2 | **Settings → AI**: upload Claude `.credentials.json` từ máy đã `claude login`. Admin có thể publish một credential **dùng chung** cho member |
| 3 | **Settings → Connection**: thêm kết nối provider — Azure DevOps cần **URL cấp tổ chức** + Project + PAT. Bấm **Test connection** rồi **Save** |
| 4 | **Settings → Execution target = Local Agent**, rồi vào **Local Agent** lấy mã ghép nối |
| 5 | Trên máy tester: `npx @q-agent/agent` → `qagent-agent pair <mã>` → `qagent-agent start` |

> ⚠️ Bản Docker **không đóng gói Playwright** trong container `api`. Chọn chạy phía server sẽ fail —
> test phải chạy qua **Local Agent**. Đây cũng là lý do đúng đắn: app sau SSO/MFA cần người đăng nhập
> thật, và session của tester **không rời khỏi máy đó** — chỉ spec, kết quả và bằng chứng đi về server.

### Bước 1 — Cấu hình project (một lần cho mỗi project)

Vào **Project Details**:

| Tab | Việc cần làm |
|---|---|
| **Settings** | Thêm **repository** của project (tự phát hiện từ Azure DevOps / GitHub, hoặc thêm tay). Đặt base URL, URL từng môi trường, và **test account** (mật khẩu mã hoá, che trên UI) |
| **Project Knowledge** | Build **Knowledge Base cho từng repository** |

**Knowledge Base là bước quan trọng nhất.** Q-Agent clone repo và cho AI đọc mã nguồn thật, lưu lại:
stack đang dùng, kiến trúc, **route thật**, **selector thật**, luồng đăng nhập, page object và fixture
có thể dùng lại. Nhờ đó spec sinh ra chạy được gần như không cần sửa tay.

> Build mất khoảng vài phút tới ~20 phút tuỳ repo. Admin có thể build sẵn project mẫu trong
> **namespace dùng chung** để member **clone** lại, đỡ phải build lại từ đầu.

### Bước 2 — Đồng bộ ticket và tạo Run

1. Vào **Tickets** → bấm **Sync** để kéo ticket từ provider.
2. Chọn ticket, bấm **Create run**. Có bốn cách chọn phạm vi:

| Phạm vi | Dùng khi |
|---|---|
| **Single** | Một ticket |
| **Selected** | Nhiều ticket tự chọn |
| **Assigned** | Toàn bộ ticket đang gán cho mình |
| **Sprint** | Cả sprint |

> Ticket nào có **acceptance criteria** viết rõ thì test case sinh ra tốt hơn hẳn — đây là đầu vào
> quan trọng nhất của bước 1.

### Bước 3 — Duyệt test case (Review Center)

AI sinh test case xong, run **dừng lại** ở trạng thái review. Mở **Review Center** — màn hình được
thiết kế giống review pull request:

| Hành động | Kết quả |
|---|---|
| **Approve** | Case được đưa vào các bước sau |
| **Edit** | Sửa nội dung case rồi duyệt |
| **Reject** | Loại case đó |

Kiểm tra cột **truy vết AC → case**: ticket có 5 acceptance criteria mà chỉ 4 cái được phủ thì
hiện ra ngay tại đây.

> **Không có case nào đi tiếp mà chưa được người duyệt.** AI viết nháp, QC/QA ký duyệt.

### Bước 4 — Đẩy case lên provider (Link)

Case đã duyệt được **tạo thật trên Azure DevOps** và gắn vào work item gốc.
Có chế độ **chạy thử (dry run)** để xem trước sẽ tạo những gì trước khi ghi vào dữ liệu thật.

### Bước 5 — Sinh và chạy automation

1. **Automation** — chọn chế độ (mặc định **live-authoring**). AI dựng spec Playwright.
   Spec được tổ chức thành một **project Playwright hoàn chỉnh** — `pages/`, `components/`,
   `fixtures/`, `data/`, `utils/` — nên ticket sau dùng lại được của ticket trước.
2. **Execution** — chạy spec trên Local Agent, log hiện trực tiếp.
   Fail vì selector đổi thì AI đọc lỗi, sửa và chạy lại (**self-heal**, có giới hạn số vòng).
3. Có **chat theo từng spec** để yêu cầu sửa một chỗ cụ thể mà không phải sinh lại toàn bộ.

Khi test fail, AI phân loại nguyên nhân: `test_defect` · `product_defect` · `flaky` ·
`environment` · `timeout` — để không mất thời gian sửa test khi lỗi thật nằm ở sản phẩm.

> Có một **cửa chặn placeholder**: spec chứa selector do AI tự nghĩ ra sẽ bị chặn, không cho đi tiếp.

### Bước 6 — Bằng chứng và trả kết quả

| Tab | Xem gì |
|---|---|
| **Evidence** | Ảnh màn hình, video, Playwright trace, console, network, DOM — theo từng case. Có chú thích ảnh tự động |
| **Publish** | Soạn comment kết quả và đẩy về ticket gốc, kèm bằng chứng; chuyển trạng thái ticket nếu muốn |
| **Reports** | Báo cáo tổng hợp của run |

### Lưu ý vận hành quan trọng

- **Một run đầy đủ mất khoảng 5–15 phút.** Bước build Knowledge Base lâu hơn, nhưng chỉ làm một lần.
- **Mỗi lần gọi AI đều tốn chi phí.** Token và chi phí được ghi theo từng lần gọi, có **ngân sách theo tuần**.
- **Test chạy trên Local Agent**, nên máy tester phải đang bật và đã `qagent-agent start`.
- **Knowledge Base cũ đi thì spec kém đi.** Mã nguồn đổi nhiều thì build lại.
- Dữ liệu trên đĩa **tách theo từng người dùng** — spec, evidence, knowledge, repo, session
  của bạn là của riêng bạn; chỉ namespace dùng chung là do admin quản.

---

## 3. Giá trị mang lại — vì sao nên dùng

| Giá trị | Trước (làm tay hoặc tự hỏi AI) | Với Q-Agent |
|---|---|---|
| **Viết test case** | Đọc yêu cầu, gõ từng case, nhập tay vào Azure DevOps | AI sinh theo đúng định dạng, có truy vết AC, đẩy lên provider tự động |
| **Chất lượng đầu ra** | Ai viết prompt kỹ thì tốt, ai viết sơ sài thì phải làm lại | Skill built-in cho từng bước — ai chạy cũng ra kết quả tương đương |
| **Spec Playwright** | AI đoán selector, chạy là fail, sửa lại từ đầu | Live-authoring chạy thật trước, pass rồi mới sinh spec |
| **Bảo trì automation** | UI đổi một selector là một loạt test đỏ, sửa tay | Self-heal tự sửa; spec là project có page object nên sửa một chỗ |
| **Bằng chứng kiểm thử** | Chụp màn hình, dán vào ticket bằng tay | Thu tự động và comment về ticket kèm bằng chứng |
| **Kiểm soát** | — | Không case nào đi tiếp khi chưa có người duyệt |
| **Đo lường** | Không có số liệu | Token, chi phí, thời gian theo từng run; ngân sách theo tuần |

**Điểm cộng dồn theo thời gian.** Page object, component và fixture do ticket trước tạo ra được ticket
sau dùng lại. Bộ automation lớn dần theo từng ticket thay vì phình thành hàng trăm file trùng lặp.
Và skill là tài sản chung — thấy test case hay bỏ sót một loại case thì sửa `test-case-generator`
một lần, cả nhóm được hưởng.

**Điều Q-Agent không làm.** Nó không thay QC/QA. Nó làm phần gõ và phần lặp; phán đoán "case này đã đủ
chưa, rủi ro nằm ở đâu" vẫn là việc của con người — và bước Review Center tồn tại chính để bảo vệ điều đó.

---

← Quay lại [tổng quan giải pháp](README.md) · [Bộ tài liệu dự thi](product/README.md)

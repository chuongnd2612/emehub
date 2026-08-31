# 2.2 User Flow

Ba flow. Flow A chạy một lần cho mỗi workspace/project; flow B là golden path hằng ngày;
flow C là nhánh cho app cần đăng nhập thật.

---

## Flow A — Onboarding & cấu hình *(admin, một lần)*

**Entry point:** admin mở `https://hub.chuongnd.click`, chưa có tài khoản nào.

| # | User action | System response | AI |
|---|---|---|---|
| A1 | Đăng ký tài khoản đầu tiên | Tài khoản này là `admin`. Refresh cookie HttpOnly được set | — |
| A2 | *(tuỳ chọn)* Bật TOTP 2FA ở Profile | Hiển thị QR + recovery code | — |
| A3 | Integrations → dán PAT Azure DevOps | Hub validate PAT → **tự liệt kê organisation** | — |
| A4 | Chọn organisation | Hub đổ về danh sách project của organisation đó | — |
| A5 | **Test connection** (form còn là nháp) | Gọi thử provider, trả kết quả trước khi Save | — |
| A6 | Save | PAT encrypted at rest. `GET /connections` từ đây trả `hasPat: true` | — |
| A7 | Claude → upload `.credentials.json`, hoặc publish credential shared | Chip credential trên header đổi trạng thái ngay (`Personal` / `Shared` / `Not set`) | — |
| A8 | Projects → New project: key, base URL, environment, test account, binding connection | Test-account password lưu encrypted, che trên UI | — |
| A9 | Tab Repository → thêm repo | Repo được phát hiện từ connection đã bind, hoặc thêm tay | — |
| A10 | Tab Knowledge → **Build** | Hub clone repo vào workspace theo owner, spawn `project-bootstrap` qua Claude CLI ở background. Trạng thái → `indexing`, UI poll tiến độ theo bước | ✅ đọc source thật |

**Decision point A-D1 — trạng thái knowledge sau build**

| Kết quả | Đi tiếp |
|---|---|
| `indexed` | Sang Flow B |
| `error` | UI hiện `lastError` actionable (repo không clone được / credential thiếu / timeout). Sửa rồi Build lại |
| `stale` *(sau này)* | Source đã đổi. Build lại trước khi sinh spec |

**Success path:** knowledge = `indexed`, confidence score hiển thị, có `knowledge.md` và
`knowledge.json`.
**Failure path:** `error` — không có nhánh nào cho phép đi tiếp với knowledge chưa build.

**End state:** một project cấu hình đủ, dùng lại được cho mọi ticket sau. Member khác **clone**
project mẫu này từ shared namespace thay vì build lại (~20 phút build được thay bằng một thao tác).

---

## Flow B — Golden path: một ticket từ đầu đến cuối *(QC/QA)*

**Entry point:** Trang login ở hub, thấy card Q-Agent ở trạng thái `handoffReady`, bấm **Launch** →
vào Q-Agent đã authenticated (không login lần hai).

```
Launch ──► Tickets ──► Sync ──► chọn ticket ──► Create run
                                                     │
                        ┌────────────────────────────┘
                        ▼
  [1] Analyze & Generate ──AI──► test case (pending) + mapping AC→case
                        │
                        ▼
  [2] Review Center ────────── GATE 1: người duyệt từng case ──┐
                        │                                       │
              approved ─┤                          rejected ────┘ (sửa hoặc bỏ)
                        ▼
  [3] Link ─────────────────── GATE 2: local mode (dry-run) hay write thật?
                        │
                        ▼
  [4] Automation ──AI──► live-harness: chạy thật trên app ──► emit spec
                        │                                        │
                        │                          placeholder gate
                        │                     passed ─┴─ blocked / rejected ──► quay lại
                        ▼
  [5] Execution ──► chạy spec ──► fail? ──AI──► failure class + heal (≤3) ──► chạy lại
                        │
                        ▼
  [6] Evidence ──► screenshot · video · trace · console · network
                        │
                        ▼
  [7] Publish ──────────────── GATE 3: preview comment ──► ticket + status mapping
```

### Chi tiết từng bước

| # | User action | System response | AI interaction |
|---|---|---|---|
| B1 | **Sync** ticket từ Azure DevOps | Ticket được normalise và lưu ở hub: id, title, type, status, assignee, description, AC, comment, link | — |
| B2 | Chọn ticket → **Create run** (1 ticket / nhiều ticket / cả sprint) | Run được tạo, trạng thái = bước hiện tại | — |
| B3 | Chờ | `requirement-analyst` đọc AC; `test-case-generator` sinh case theo format Azure DevOps; `test-case-reviewer` soát lại | ✅ input: AC + knowledge base (route, selector, auth flow thật) |
| B4 | Xem cột mapping **AC → case** | Reviewer thấy AC nào chưa có case nào cover | — |
| B5 | **Review Center**: duyệt / sửa / từ chối từng case; đổi automation type | Chỉ case `approved` mang sang bước sau. Case `Manual` không bao giờ đem sinh spec | — |
| B6 | **Link** — chọn local mode hoặc write thật | Local mode: ghi local, không đụng provider. Write thật: tạo test case trên Azure DevOps và gắn vào work item gốc | — |
| B7 | **Automation** — mode `live-harness` (mặc định) | Agent mở Chrome đã authenticated qua `browser-harness`, thực thi từng step trên app thật, resolve element qua accessibility tree, tạo test data nếu thiếu, verify hiệu ứng thật (URL đổi) trên **chính selector sắp emit**, rồi mới sinh spec | ✅ **magic moment** |
| B8 | — | Placeholder gate pre-flight: selector bịa, `TODO` stub, URL placeholder → verdict `blocked` / `rejected` với lý do hiển thị | ✅ |
| B9 | **Execution** — chạy spec, xem log trực tiếp | Fail → `execution-analyzer` gán failure class (`test_defect` / `product_defect` / `flaky` / `environment` / `timeout`); heal có grounding DOM, tối đa 3 lần | ✅ |
| B10 | **Evidence** | Screenshot (có annotate), video, trace, console, network | ✅ `screenshot-annotator` |
| B11 | **Publish** — xem preview comment | `ticket-comment-generator` dựng comment; người duyệt rồi mới gửi; status mapping cấu hình được | ✅ |

### Decision points

| ID | Câu hỏi | Nhánh |
|---|---|---|
| B-D1 | Knowledge base có `indexed` không? | Không → dừng, quay về Flow A10 |
| B-D2 | Case này đã đủ và đúng chưa? *(người)* | Approve → đi tiếp · Sửa → approve · Reject → không đi tiếp |
| B-D3 | Case này automation được không? *(người)* | `Playwright`/`Selenium`/`Cypress` → sinh spec · `Manual` → dừng ở test case |
| B-D4 | Push lên provider thật hay dry-run? *(người)* | Local mode → không đụng provider · Write → tạo case trên ADO |
| B-D5 | Live-harness đi hết được test case không? | Có → emit spec · Không → báo bước fail, không emit spec sai |
| B-D6 | Spec qua placeholder gate không? | `passed` → execution · `blocked` → cần grounding (rebuild KB hoặc exploration pass) · `rejected` → sinh lại |
| B-D7 | Test đỏ vì spec sai hay product sai? | `test_defect` → heal · `product_defect` → báo cáo, không heal · `flaky`/`environment`/`timeout` → xử lý riêng |
| B-D8 | Comment đã đúng chưa? *(người)* | Gửi · Sửa · Không gửi |

**Success path:** ticket có test case đã duyệt trên Azure DevOps, spec Playwright chạy green,
evidence đính kèm, comment kết quả trên work item.

**Failure paths — mỗi nhánh dừng ở một trạng thái đọc được, không fail lặng:**

| Failure | Trạng thái | Người dùng làm gì |
|---|---|---|
| Knowledge chưa build | Bước 1 chặn | Build knowledge |
| Claude credential `none` hoặc `expired` | Run không start | Upload credential hoặc chuyển sang shared |
| Vượt cost ceiling / turn cap / timeout | Run dừng có lý do | Tăng ngân sách hoặc thu hẹp scope |
| Live-harness không đi hết được test case | Bước 4 dừng | Kiểm tra test account, base URL, hoặc chuyển sang mode `blind` |
| Spec `blocked` ở placeholder gate | Bước 4 dừng | Rebuild KB hoặc chạy exploration pass |
| Heal 3 lần vẫn đỏ | Bước 5 dừng | Đọc failure class; nếu `product_defect` thì đây là kết quả đúng |
| Provider từ chối write | Bước 3 hoặc 7 dừng | Kiểm tra scope của PAT |

**End state:** Run ở trạng thái hoàn tất; PM nhìn work item là thấy đủ test case, kết quả chạy
và evidence. Page object, component và fixture sinh ra trong run này **dùng lại được** cho ticket
sau — bộ automation lớn dần thay vì phình thành file trùng lặp.

---

## Flow C — App sau SSO/MFA: Local Agent

**Entry point:** app cần đăng nhập thật (OTP, SSO nội bộ) nên không thể chạy trên server.

| # | User action | System response |
|---|---|---|
| C1 | Settings → Execution target = **Local Agent** | Q-Agent chuyển hướng job sang device đã pair |
| C2 | Local Agent → lấy **pairing code** | App mint code ngắn hạn |
| C3 | Trên máy tester: `npx @q-agent/agent` → `qagent-agent pair <code>` | CLI đổi code lấy token per-device lưu tại `~/.qagent-agent/config.json`; server chỉ giữ **hash** trên row `AgentDevice` thuộc user đó |
| C4 | `qagent-agent start`; đăng nhập app thủ công trong headed browser | Cookie và `storageState` ở lại trên máy tester |
| C5 | Chạy Flow B bình thường | Spec thực thi tại chỗ; chỉ spec, kết quả và evidence đi về server |
| C6 | *(khi cần)* Revoke device từ app | Device đó ngừng nhận job ngay |

**Decision point C-D1:** app có chạy được headless trên server không?
Có → execution trên server. Không → Local Agent. Đây cũng là lý do image `api` **cố tình không**
đóng gói Chromium.

**End state:** test chạy được trên app doanh nghiệp mà browser session của tester không bao giờ
rời khỏi máy tester.

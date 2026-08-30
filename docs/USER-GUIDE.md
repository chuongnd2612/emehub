# Hướng dẫn sử dụng

Đường đi từ lần đăng nhập đầu tiên tới lúc kết quả execution quay về ticket.

Tài liệu phủ hai ứng dụng: **EmeHub** — identity, credential, project — và **Q-Agent** — pipeline
QA. D-Agent chạy trong cùng suite nhưng chưa consume cấu hình từ hub, nên không nằm trong luồng
này.

---

## 0. Trước khi bắt đầu

Ba ứng dụng nằm sau một origin, agent mount theo path.

| Ứng dụng | Đường dẫn |
|---|---|
| EmeHub | `https://hub.chuongnd.click` |
| Q-Agent | `https://hub.chuongnd.click/qagent/` |
| D-Agent | `https://hub.chuongnd.click/dagent` |

Tài khoản demo: [ACCOUNT.md](ACCOUNT.md). Đăng nhập một lần ở EmeHub dùng được cả ba.

**Cần chuẩn bị:**

- **PAT** của Azure DevOps (hoặc Jira / GitHub) — để sync ticket.
- **`.credentials.json`** của Claude CLI đang đăng nhập — để chạy các AI action. Bỏ qua được nếu
  admin đã publish shared credential ([§2](#2-claude-settings)).
- **Node.js** trên máy, nếu chạy Playwright bằng Local Agent ([§10](#10-local-agent)).

---

# Phần A — EmeHub

## 1. Đăng nhập và layout

Đăng nhập bằng email + password, thêm TOTP nếu tài khoản đã bật 2FA.

Sidebar chia hai group:

| WORKSPACE | |
|---|---|
| **Overview** | Trạng thái từng agent, số liệu tổng, nút Launch |
| **All projects** | Danh sách project và bảng so sánh cross-project |
| **Unassigned** | Work item chưa thuộc project nào |

| PLATFORM | |
|---|---|
| **Claude Settings** | Credential và model |
| **Authentication** | Session và sign-in method |
| **User Management** | Member của workspace |
| **Integrations** | Kết nối Azure DevOps, Jira, GitHub |
| **Settings** | Appearance và product availability |

Project tree nằm ngay dưới **All projects**, với count đọc từ dữ liệu thật.

Header phải là **chip credential Claude**: mode đang dùng (Personal / Shared), phần trăm session
limit và weekly limit còn lại. Bấm vào để mở popover và nhảy sang Claude Settings.

Chip user ở góc dưới trái dẫn tới **Your account**.

---

## 2. Claude Settings

Không có credential thì mọi AI action phía sau không chạy.

### 2.1. Chọn source

Hub resolve theo thứ tự **`own` → `shared` → `none`**:

- **Personal** — upload `.credentials.json` do Claude CLI tạo ra trên máy bạn.
- **Shared** — credential do admin publish, ở mục **SHARED CLAUDE ACCOUNTS**. Chỉ admin thấy vùng
  upload; member chỉ dùng.
- **Không có** — hub báo tường minh là chưa gắn credential nào.

Switch **Shared | Personal** đổi mode tức thì; chip trên header phản ánh ngay.

### 2.2. Đọc status cho đúng

| Status | Nghĩa |
|---|---|
| `active` | Đang dùng được |
| `expiring` | Sắp hết hạn |
| `refreshable` | Access token quá `expiresAt` **nhưng có refresh token** — Claude CLI tự renew ở lần chạy tới. Đây là trạng thái bình thường. |
| `expired` | Claude CLI thật sự bị reject. Đây mới là lúc phải upload lại. |

Access token của Claude OAuth sống vài giờ, nên một file thật gần như luôn quá hạn ngay khi
upload. Khi CLI renew, agent ghi token mới ngược về hub.

### 2.3. Test và usage

Nút test gọi thử một call để xác nhận credential chạy được. Tab **Models** chọn model mặc định.
Mỗi call ghi token count và cost, roll up lên chip credential.

---

## 3. Integrations

Mỗi connection cần: loại provider, org hoặc base URL, và **PAT** — encrypt at rest ngay khi lưu.

Connection tự khai **capability**: `work_item` (cấp ticket) và `repository` (cấp repo). Nên một
project bind được hai provider khác nhau cho hai việc khác nhau — ví dụ ticket từ Azure DevOps,
repo từ GitHub.

PAT không rời khỏi hub; hub proxy mọi provider call. Sau khi lưu, UI chỉ báo `hasPat: true`. Đổi
token thì nhập token mới.

Dùng chức năng test connection để xác nhận PAT còn hiệu lực trước khi đi tiếp.

---

## 4. Project và repository

Tạo project ở **All projects**. Mỗi project có sáu tab, mỗi tab là một path segment
(`/app/projects/<id>/<tab>`):

| Tab | Nội dung |
|---|---|
| **Overview** | Trạng thái tổng quan |
| **Project knowledge** | Build và xem Knowledge Base |
| **Repository** | Repo của project; một repo được đánh dấu default |
| **Agents** | Agent đang bind với project |
| **Tickets** | Work item; provider derive từ project |
| **Settings** | Base URL, URL theo environment, test account, extra key/value |

**Repository** — thêm từ provider có capability `repository`, hoặc nhập tay. Repo default là app
được nhắm tới khi một run không chỉ định repo.

**Settings** quyết định chất lượng output: base URL, URL theo environment, test account (password
encrypt at rest, mask trong UI) và extra key/value đi thẳng vào prompt của các AI action phía sau.

---

## 5. Project knowledge

Build KB ở tab **Project knowledge**. Việc này chạy **trên hub** — artefact duy nhất hub tự build,
vì hub đã sở hữu toàn bộ input ([ADR 0007](adr/0007-knowledge-builds-run-on-the-hub.md)).

Hub materialise credential Claude vào một directory chmod chặt, chạy skill `project-bootstrap` qua
Claude CLI, và skill này traverse source thật của repo để rút ra stack, kiến trúc, domain, route,
selector, auth flow, environment, và các Page Object / fixture tái dùng được. Output là
`knowledge.md` + `knowledge.json`, **per repository**.

Một lượt build đầy đủ tốn khoảng 20 phút. Build một lần, rebuild khi repo đổi đáng kể.

**Clone thay vì build lại.** Nếu admin đã build project mẫu trong shared namespace, member clone
nó về scope của mình — kèm `ProjectConfig`, test account đã encrypt và artefact trên đĩa.

---

## 6. Ticket

Tab **Tickets** hiện work item sync từ provider. Provider **derive từ project**, không phải một ô
chọn.

Ticket ở hub là read-only: mô tả, acceptance criteria, comment, attachment, label, priority,
status, linked PR. Nơi sửa nó là provider.

**Unassigned** ở sidebar chứa work item chưa thuộc project nào — chúng vẫn phải xuất hiện ở đâu
đó.

---

## 7. Quản trị workspace

**User Management** — hub có đúng hai role: `admin` và `member`. Invite tạo tài khoản ngay, không
có hàng đợi pending.

**Authentication** — mỗi session là một lần đăng nhập trên một device, kèm user agent và IP.
Revoke một session là log out device đó khỏi **mọi** agent, vì mỗi access token mang `sid`.

**Settings** — appearance (bốn accent, light/dark) và **product availability**. Tắt một product
thì app, edge proxy và landing page đều chặn nó.

**Your account** — thông tin cá nhân, đổi password, bật 2FA (TOTP).

---

## 8. Launch sang Q-Agent

Từ **Overview**, bấm **Launch** trên card Q-Agent. Không có màn đăng nhập thứ hai: hub mint access
token audience-scoped cho Q-Agent, Q-Agent validate locally.

---

# Phần B — Q-Agent

## 9. Layout và project containment

> **Điều hướng của Q-Agent đã refactor theo project** (ADR 0015). Không còn mục **Tickets**,
> **Runs** hay **Reports** ở cấp workspace — chúng là **tab của một project**. Câu hỏi
> cross-project "cái gì đang chạy" chuyển sang comparison table trên Dashboard.

Sidebar, từ trên xuống:

| | |
|---|---|
| **Back to EmeHub** | Quay lại hub |
| **WORKSPACE › Dashboard** | Metric tổng và comparison table cross-project |
| **PROJECTS** | Project tree — mở một project ra thấy đúng sáu tab của nó |
| **All projects** | Danh sách project |
| **Getting Started** | Checklist thiết lập |
| **Local Agent** | Pairing và trạng thái device |
| **Settings** | Cài đặt chung |

Và một group **ADMIN** riêng, chỉ admin thấy:

| | |
|---|---|
| **Users** | Quản lý user |
| **Claude credentials** | Credential phía Q-Agent |
| **Shared workspace** | Shared namespace — admin build project mẫu ở đây, member clone về |
| **Audit Log** | Nhật ký append-only |

Màn hình run-scoped (Review, Automation, …) **không** có mặt trong sidebar — đó là thứ ngăn việc
mở một trong số chúng khi chưa có run.

**Sáu tab của một project** (`/projects/<guid>/<tab>`):

| Tab | Nội dung |
|---|---|
| **Overview** | Metric của project: ticket count, active run, pass rate, knowledge confidence |
| **Tickets** | Work item của project |
| **Runs** | Các run của project |
| **Project Knowledge** | KB per repository |
| **Connection** | Provider binding và cấu hình của project |
| **Reports** | Báo cáo |

**Ngôn ngữ UI** đổi được EN | VI ngay trên header. Đây là display preference lưu ở `localStorage`,
không ảnh hưởng dữ liệu, provider payload hay artefact sinh ra.

---

## 10. Run — thực thể trung tâm

Mọi thứ sau bước chọn ticket đều thuộc về một **Run**. Tạo run từ tab **Tickets** của project:
một ticket, một nhóm đã chọn, toàn bộ ticket được assign cho mình, hoặc cả sprint.

Run đi qua tám stage, mỗi stage là một path segment
(`/projects/<guid>/runs/<runId>/<stage>`). **PipelineRail** hiện stage hiện tại trên mọi màn hình
thuộc run.

```
processing → review → sync → automation → executing → evidence → comment → done
```

### `processing` — phân tích và sinh test case

Không cần thao tác. `requirement-analyst` đọc ticket + KB ra requirement analysis;
`test-case-generator` biến nó thành test case kiểu Azure DevOps.

Stage này cố ý sinh **ít**: chỉ happy path, mỗi acceptance criterion một kịch bản thành công. Nó
**không** sinh edge case, negative case, permission matrix hay regression suite — đó là việc của
`test-case-reviewer` ở stage sau.

### `review` — Review Center

Test case sinh ra ở trạng thái `pending`. Ở đây bạn đọc và sửa từng case, **approve** hoặc
**reject**, chỉnh **automation type** (`Playwright` / `Selenium` / `Cypress` / `Manual`), và chạy
thêm một AI review pass (`test-case-reviewer`) để mở rộng coverage.

Chỉ case `approved` đi tiếp. Case `Manual` không bao giờ được đem sinh spec.

### `sync` — Create & Link

Tạo test case đã approve lên provider và link với work item gốc. Có **local mode** (dry-run): ghi
local, không write lên provider.

### `automation` — sinh spec Playwright

Hai **authoring mode**:

**`live-harness`** — agent drive browser thật đã authenticated qua CLI `browser-harness`: thực thi
từng step trên app đang chạy, resolve element qua accessibility tree, ghi **selector thật** theo
thứ tự `data-testid` → ARIA role + accessible name → label → CSS ổn định, tạo test data nếu thiếu,
rồi mới emit spec.

Điểm mấu chốt: nó verify **selector**, không verify toạ độ. Mỗi interaction được dispatch trực
tiếp trên chính selector sắp emit và kiểm tra hiệu ứng thật.

**`blind`** — sinh từ KB + Project Config, rồi self-heal: feed failure kèm live DOM ngược lại,
fix có mục tiêu, re-run — tối đa 3 attempt, timeout rút ngắn, model rẻ. Heal pass có grounding DOM
ghi entry **verified-at-runtime** ngược vào KB.

**Placeholder gate** chặn trước execution: selector bịa, `TODO` stub, URL placeholder. Verdict
`passed` / `blocked` / `rejected`. Spec `blocked` cần grounding thêm — rebuild KB hoặc chạy
exploration pass.

Cả hai mode bounded bằng cost ceiling, turn cap và wall-clock timeout.

### `executing` — chạy thật

Playwright chạy suite đã approve. Mỗi case có status `pending` / `running` / `pass` / `fail`.
Target là **Local Agent** (mặc định) hoặc server.

`execution-analyzer` gán **failure class** cho mỗi case fail:

| Class | Nghĩa |
|---|---|
| `test_defect` | Spec sai |
| `product_defect` | App sai — đây mới là bug thật |
| `flaky` | Không ổn định |
| `environment` | Lỗi môi trường |
| `timeout` | Quá thời gian |

### `evidence`

Per case: screenshot, video, Playwright trace, console log, network log, summary. Group theo
ticket. Screenshot **annotate** được (rectangle / arrow / highlight / circle / text) để đính vào
comment.

### `comment`

Comment kết quả được chuẩn bị và preview trước khi publish lên work item gốc. Status mapping cấu
hình được (ví dụ *Ready for QA* → *Testing* → *Passed* / *QA Failed*).

### `done`

Report tổng hợp: kết quả chung, summary theo ticket, pass/fail count, AI failure analysis, timing,
environment, link evidence. Xem lại ở tab **Reports** của project.

---

## 11. Local Agent

App sau SSO/MFA cần một người đăng nhập thật trong headed browser. Local Agent execute spec ngay
trên máy tester, nên cookie và `storageState` không rời khỏi device — chỉ spec, kết quả và
evidence đi ngược về server. Nó cũng chạy agent-side self-heal, DOM exploration, live authoring và
manual-login capture.

### Device pairing (bắt buộc, làm một lần)

1. Vào màn **Local Agent**, lấy **pairing code** ngắn hạn.
2. Trên máy bạn: `npx @q-agent/agent` — hoặc bản desktop Electron, **hiện chỉ có installer
   Windows**.
3. Nhập code. CLI đổi nó lấy token per-device lưu tại `~/.qagent-agent/config.json`; server chỉ
   giữ hash.
4. Mọi agent job scope theo device owner. Admin revoke token bất cứ lúc nào.

### Manual login

Với app sau SSO/MFA: Local Agent mở headed browser, **bạn tự đăng nhập**, session được giữ tại
chỗ cho các lần chạy sau. Agent **không bao giờ** tự gõ password hay MFA code, và **không bao giờ**
chạy trên production.

---

## 12. Khi có gì đó không chạy

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| AI action không chạy | Chưa có Claude credential, hoặc status `expired`. Vào **Claude Settings**, đổi sang Shared hoặc upload lại. |
| Credential hiện màu cảnh báo nhưng vẫn chạy | Status `refreshable` — bình thường. CLI tự renew. Không cần làm gì. |
| Sync ticket không ra gì | PAT hết hạn hoặc thiếu scope. Test lại connection ở **Integrations**. |
| Test case chung chung, nhiều chỗ trống | Chưa build KB, hoặc **Project settings** thiếu base URL / test account. Cả hai đi thẳng vào prompt. |
| Spec `blocked` | Placeholder gate bắt được selector chưa có grounding. Rebuild KB hoặc dùng `live-harness` thay vì `blind`. |
| Không execute được | Local Agent chưa pair hoặc chưa chạy. Xem [§11](#11-local-agent). |
| Fail ở bước login trên app sau SSO | Cần một lần manual login trên Local Agent. |
| Không tìm thấy Tickets / Runs ở sidebar Q-Agent | Chúng là **tab của project**, không còn ở cấp workspace. Mở project trong project tree. |
| Cần log out một device | **Authentication** trong EmeHub — revoke session là log out khỏi cả ba ứng dụng. |

---

## Đọc tiếp

- [ACCOUNT.md](ACCOUNT.md) — link truy cập và tài khoản demo
- [SELLING-POINTS.md](SELLING-POINTS.md) — kiến trúc và điểm khác biệt
- [CONTEXT.md](CONTEXT.md) — vocabulary dùng chung
- [INTEGRATION.md](INTEGRATION.md) — contract giữa hub và agent

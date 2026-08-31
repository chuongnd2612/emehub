# EMEHUB

**Đội:** `CLGT-EAM` · **Thành viên:** `Nguyễn Đình Chương - Đào Văn Linh - Đồng Huỳnh Giao`

**Source code:** [`chuongnd2612/emehub`](https://github.com/chuongnd2612/emehub) (hub, repo này) ·
[`chuongnd2612/q-agent`](https://github.com/chuongnd2612/q-agent) (agent QC/QA) — cả hai public,
branch `master`.

| Tài liệu | Nội dung |
|---|---|
| **Tài liệu này** | Ý tưởng, bài toán, giải pháp và cách sản phẩm hoạt động |
| [**Bộ tài liệu dự thi**](product/README.md) | Product brief, PRD, user flow, AI solution, architecture, evaluation, roadmap, metrics, demo script, pitch deck |
| [**Hướng dẫn sử dụng Q-Agent**](QAgent.md) | Agent cho QC/QA — từ ticket ra test case đã kiểm thử |
| [**Thông tin trải nghiệm**](ACCOUNT.md) | Link truy cập, tài khoản demo và repository |
| [**Những gì đã gỡ và chưa làm**](KNOWN-GAPS.md) | Bản ghi trung thực: tính năng đã gỡ, việc chưa xong, lỗi đã sửa |

---

## Ý tưởng

Ý tưởng không bắt đầu từ một nền tảng, mà bắt đầu từ công việc hàng ngày của chính đội.

Chúng tôi thấy DEV và QC/QA đang lặp lại quá nhiều việc tay chân quanh mỗi ticket, nên xây
hai công cụ dùng AI để tự động hoá phần lặp đó:

- **DAgent** cho DEV — từ ticket ra pull request.
- **QAgent** cho QC/QA — từ ticket ra test case đã kiểm thử kèm bằng chứng.

Hai công cụ chạy được và cải thiện năng suất thật. Nhưng khi dùng, một vấn đề khác lộ ra: **không
có chỗ nào để quản lý các tool nội bộ này.** Mỗi tool có tài khoản riêng, PAT Azure DevOps
riêng, credential Claude riêng, cấu hình project riêng. Cùng một thông tin phải khai lại ở từng nơi,
và không ai nắm được ai đang dùng tool gì với quyền gì.

**EmeHub ra đời từ đó** — một nơi để quản lý các tool AI nội bộ của công ty và những thứ chúng
dùng chung. Khai báo một lần, tool nào cũng dùng được.

## Bài toán

Ba bài toán, giải quyết theo đúng thứ tự đó.

**Bài toán 1 — công việc lặp quanh mỗi ticket.**
QC/QA gõ lại yêu cầu thành test case, nhập từng case vào Azure DevOps, viết script Playwright,
chạy, chụp bằng chứng, comment kết quả. DEV tạo branch, viết code, commit, push, mở PR, sửa theo
review. Phần lớn là việc tay chân; phần thực sự cần chuyên môn thì bị dồn vào thời gian còn thừa.
Riêng bảo trì automation còn tốn hơn viết mới — UI đổi một selector là một loạt test đỏ.

**Bài toán 2 — dùng AI mỗi người một kiểu.**
Khi chưa có công cụ, mỗi người tự mở chat AI và tự viết prompt. Cùng một ticket, người viết prompt kỹ
thì ra test case dùng được, người viết sơ sài thì ra một danh sách chung chung phải làm lại từ đầu.
Không có chuẩn, và không ai cải tiến được cái gì — kinh nghiệm nằm trong đầu từng người, không tích luỹ
thành tài sản của nhóm. Chất lượng đầu ra phụ thuộc vào kỹ năng viết prompt chứ không phải vào
chuyên môn QA.

**Bài toán 3 — tool nội bộ không có nơi quản lý.**
Mỗi tool tự giữ tài khoản, tự giữ PAT, tự đọc mã nguồn. Càng nhiều tool thì càng nhiều lần cấu hình
giống nhau, càng nhiều chỗ để token rò rỉ, và càng nhiều nơi phải sửa khi có người nghỉ việc.

## Giải pháp

Hai agent AI đứng trên một nền tảng chung, chạy trên hạ tầng nội bộ công ty.
Đầu vào là một ticket Azure DevOps, đầu ra là công việc đã hoàn chỉnh:

- **QAgent** trả về test case đã được duyệt, script Playwright đã chạy, capture evidence sau đó comment vào ticket.
- **DAgent** trả về một pull request đã open, với code được Claude implement.

**EmeHub** giữ những thứ cả hai dùng chung: tài khoản người dùng, credential, kết nối Azure DevOps,
project, và knowledge base của project.

**Phạm vi ở phase này:** team tập trung phát triển QAgent và DAgent — đây là phần tạo ra giá trị
trực tiếp cho công việc. EmeHub hiện làm đúng vai trò nền tảng dùng chung. Các tính năng sâu hơn
về quản lý tool và phân quyền theo từng tool sẽ triển khai ở phase sau.

---

## Cách sản phẩm hoạt động

```
   Ticket (Azure DevOps)
            │
            ▼
   ┌────────────────────────────────────────────┐
   │  EmeHub — nền tảng dùng chung              │
   │  · người dùng, phiên đăng nhập, credential │
   │  · kết nối Azure DevOps (PAT mã hoá)       │
   │  · project, repository                     │
   │  · KNOWLEDGE BASE đọc từ mã nguồn thật     │
   └───────┬────────────────────────┬───────────┘
           │                        │
      ┌────▼─────┐            ┌─────▼────┐
      │  QAgent  │            │  DAgent  │
      └────┬─────┘            └─────┬────┘
           │                        │
   test case + bằng chứng      pull request
           │                        │
           └────────► Ticket ◄──────┘
```

### 1. EmeHub — quản lý dự án, kết nối và credential

**Quản lý dự án đang tham gia.** Mỗi thành viên có danh sách project riêng của mình, cộng một
namespace dùng chung của cả nhóm. Một project gồm: mã project, base URL, các môi trường,
tài khoản test, repository, và liên kết tới kết nối provider.

**Kết nối provider theo hướng credential-first.** Người dùng dán PAT trước, hệ thống xác thực rồi
**tự liệt kê organisation** mà token đó vào được; chọn organisation thì danh sách project tự đổ về.
Không phải tự đi tìm URL organisation hay gõ tay tên project — đây là chỗ trước đây sai một ký tự
là báo lỗi mà không biết sai ở đâu. Kết nối còn test được ngay trên bản nháp chưa lưu, nên không
phải ghi đè lên cấu hình đang chạy tốt để rồi mới biết là sai.

**Fetch thông tin ticket.** Ticket được đồng bộ và chuẩn hoá đầy đủ: loại, trạng thái, độ ưu tiên,
người phụ trách, sprint, area path, epic, mô tả, **acceptance criteria**, comment, attachment và
pull request đã link. Đây là đầu vào cho cả QAgent và DAgent.

**Quản lý Claude credential dùng chung.** Admin upload một credential chung cho cả nhóm; mỗi người
dùng có thể upload credential riêng, hoặc chọn dùng credential chung — và chuyển qua lại giữa hai
lựa chọn mà không phải xoá gì. Mọi lần gọi Claude đều được ghi lại token, chi phí và độ trễ, kèm
việc nó chạy dưới credential *riêng* hay *chung*. Đây là nền để phát triển tiếp thành **pool
account**: một nhóm tài khoản Claude chia sẻ cho nhiều người dùng, có kiểm soát mức tiêu thụ.

### 2. Knowledge base — quét project để AI không phải đoán

EmeHub clone repository về và chạy skill `project-bootstrap` để **quét toàn bộ mã nguồn**, rồi lưu
thành hai bản: một bản cho người đọc và một bản có cấu trúc cho AI đọc. Nội dung là những thứ cụ thể:
công nghệ đang dùng, kiến trúc, **các route thật**, **selector thật** (`data-testid`), page object,
fixture, và luồng đăng nhập của ứng dụng.

Quá trình build đi qua các bước có thể theo dõi trực tiếp — xếp hàng, phân giải cấu hình, clone,
phân tích, ghi kết quả — và trạng thái đi từ `not_indexed` → `indexing` → `indexed`, tự chuyển sang
`stale` khi mã nguồn thay đổi. Mỗi bản knowledge base có một điểm tin cậy đi kèm.

> Đây là điểm kỹ thuật cốt lõi. Không có bước này thì model **đoán** selector từ ngữ cảnh nó nhìn
> thấy — code trông hợp lý nhưng chạy là fail. Có knowledge base thì test spec sinh ra chuẩn hơn
> nhiều vì nó dựa trên route và selector thật của chính dự án. Build một lần, cả hai agent cùng dùng.

### 3. QAgent — bộ skill built-in chạy ở từng bước

> Cách dùng từng bước: [**Hướng dẫn sử dụng Q-Agent**](QAgent.md)


QAgent không gọi AI theo kiểu một prompt chung. Nó có **14 skill được xây sẵn**, mỗi skill lo đúng
một bước trong pipeline:

| Bước | Skill |
|---|---|
| Quét project, dựng knowledge base | `project-bootstrap` |
| Phân tích yêu cầu | `requirement-analyst` |
| Sinh và soát test case | `test-case-generator`, `test-case-reviewer` |
| Lập kế hoạch automation | `automation-planner` |
| Viết page object, sửa page object hỏng | `page-object-author`, `page-object-healer` |
| Sinh và soát test spec | `automation-generator`, `automation-reviewer` |
| Phân tích kết quả chạy | `execution-analyzer` |
| Chú thích ảnh, comment ticket, báo cáo | `screenshot-annotator`, `ticket-comment-generator`, `report-generator` |

Đây là cách chúng tôi giải quyết Bài toán 2. Người dùng **không phải viết prompt** — skill đi kèm
sản phẩm, nên cùng một ticket thì ai chạy cũng ra kết quả tương đương. Chất lượng phụ thuộc vào
skill, không phụ thuộc vào kỹ năng viết prompt của từng người.

Quan trọng hơn: skill là **tài sản chung được review và cải tiến**. Thấy test case hay bỏ sót một
loại case, ta sửa `test-case-generator` một lần và cả nhóm được hưởng. Kinh nghiệm của người giỏi
nhất được viết vào skill thay vì nằm trong đầu một người. DAgent chạy theo đúng cơ chế đó, với bộ
skill riêng cho việc implement ticket và xử lý comment review.

### 4. Live-authoring — chạy thật trước, sinh spec sau

Đây là tính năng chúng tôi tâm đắc nhất, và là cách làm khác hẳn kiểu “AI sinh test rồi sửa lỗi sau”.

Sau khi test case đã được QC/QA review và duyệt, QAgent **không sinh spec ngay**. Nó mở một Chrome
đã đăng nhập sẵn và dùng `browser-harness` để **tự đi hết các bước của test case trên ứng dụng thật**:
đọc cây accessibility để tìm đúng phần tử, tạo dữ liệu test nếu cần, xác nhận từng expected result.

Với mỗi phần tử tương tác, nó ghi lại selector ổn định nhất **thật sự tồn tại trên DOM**, theo thứ tự
ưu tiên `data-testid` → ARIA role + tên → label → CSS.

**Chỉ khi đi hết test case và pass, QAgent mới sinh test spec** — dựng từ đúng những gì vừa chạy được.
Kết quả là spec chạy xanh ngay, không cần vòng heal. Spec sinh ra chạy lại được bất cứ lúc nào.

### 5. Test spec là một project Playwright hoàn chỉnh, không phải là single file

Spec sinh ra **không** nằm rải rác thành từng file độc lập. Chúng được tổ chức thành một project
Playwright hoàn chỉnh:

```
pages/        Page Object  — locator, tương tác, điều hướng
components/   Component Object — phần UI dùng lại ở nhiều trang
fixtures/     Fixture — wiring cho spec
data/         Dữ liệu test và factory
utils/        Helper riêng của dự án
config/       Cấu hình project
tests/        Test spec
node_modules/@q-agent/playwright-base   Thư viện dùng chung
```

Nghĩa là ticket sau **dùng lại được** page object, component và fixture mà ticket trước đã tạo ra.
Bộ automation lớn dần theo từng ticket thay vì phình ra thành hàng trăm file trùng lặp. Khi UI đổi,
sửa một page object là mọi spec dùng nó đều đúng theo — đây chính là chỗ automation truyền thống
tốn nhiều công nhất.

### 6. DAgent — ticket thành PR

> **DAgent không nằm trong scope bản dự thi.** Nó là **ví dụ về agent tương lai**: gắn vào cùng
> contract của hub mà không phải sửa hub. Mô tả dưới đây nói về cơ chế đó, không phải về một ứng
> dụng thứ ba đang chạy trong bản demo.


Chọn ticket, trỏ vào repo đã clone, bấm Implement. App spawn Claude Code CLI ngay trong repo đó:
tạo branch, viết code, commit, push, mở PR. Log, tiến độ, token và chi phí stream trực tiếp về
trình duyệt. Có chế độ xem kế hoạch rồi mới cho chạy, và chức năng tự sửa theo comment review của PR.

---

## Tính năng nổi bật

| Tính năng | Vì sao đáng chú ý |
|---|---|
| **Live-authoring** | Chạy thật trên browser trước, pass rồi mới sinh spec. Spec xanh ngay, không cần vòng sửa lỗi |
| **Knowledge base từ mã nguồn** | AI dùng route và selector thật của dự án, không đoán từ ngữ cảnh |
| **Spec là project Playwright** | Page object, component, fixture dùng lại được cho ticket sau; UI đổi thì sửa một chỗ |
| **14 skill built-in** | Mỗi bước một skill chuyên trách. Người dùng không phải viết prompt — hết cảnh mỗi người một kiểu, chất lượng lệch nhau |
| **Skill được review và cải tiến** | Skill là tài sản chung: sửa một lần cả nhóm được hưởng. Kinh nghiệm tích luỹ vào sản phẩm thay vì nằm trong đầu từng người |
| **Kết nối credential-first** | Dán PAT là tự ra organisation và project, test được cả khi chưa lưu |
| **Claude credential dùng chung** | Admin cấp credential chung, user dùng chung hoặc dùng riêng; có ghi nhận token và chi phí từng lần gọi |
| **Con người ký duyệt** | QAgent không đẩy case nào đi tiếp khi chưa có người duyệt; DAgent chặn ở bước kế hoạch |

Ba điều đứng sau các tính năng trên:

**Con người giữ quyền quyết định.** AI làm phần lặp, người làm phần phán đoán. Test case phải qua
Review Center; DAgent có chế độ chặn trước khi động vào code.

**AI làm việc trên dữ liệu thật, không đoán.** Knowledge base từ mã nguồn, cộng live-authoring chạy
thật trên browser — đó là lý do output dùng được chứ không phải sửa lại từ đầu.

**Có chỗ để quản lý tool nội bộ.** Tool thứ ba cắm vào là chạy, không phải khai báo lại người dùng,
credential hay knowledge base. Nếu mỗi tool tự quản lý những thứ đó thì n tool là n lần cấu hình
giống nhau và n chỗ để token rò rỉ.

---

## Bảo mật và triển khai

Toàn bộ **self-hosted** — chạy bằng một lệnh `./suite.sh up -d --build`, ba ứng dụng sau một cổng
vào duy nhất. Dữ liệu ra ngoài chỉ có lời gọi tới Claude API.

PAT Azure DevOps được mã hoá và **không rời khỏi EmeHub** — API chỉ trả về `hasPat: true`,
agent muốn gọi provider thì đi qua hub. Khoá ký token và khoá mã hoá dữ liệu là hai khoá riêng.
Thiếu khoá thì hệ thống từ chối khởi động thay vì tự sinh khoá tạm.

---

## Hiện trạng

EmeHub đã chạy đầy đủ trên endpoint thật (~408 test backend). QAgent chạy đủ 7 bước pipeline.
DAgent chạy được từ ticket tới PR. Cả ba lên cùng lúc bằng một lệnh.

Việc chưa xong, và là chủ ý của phase này: hai agent **chưa chuyển hẳn sang đọc cấu hình từ hub** —
hiện chạy song song với hub. Phần quản lý tool và phân quyền theo từng tool ở EmeHub cũng chưa làm.

Bước tiếp theo: hoàn tất cutover cho QAgent và DAgent, rồi mở rộng EmeHub thành nơi quản lý
mọi tool AI nội bộ của công ty.

## Đọc tiếp

| Tài liệu | Nội dung |
|---|---|
| [Hướng dẫn sử dụng Q-Agent](QAgent.md) | Pipeline 7 bước, cấu hình project, knowledge base, live-authoring |
| [Thông tin trải nghiệm](ACCOUNT.md) | Link truy cập, tài khoản demo và repository |
| [Bộ tài liệu dự thi](product/README.md) | PRD, user flow, AI solution spec, architecture, evaluation, roadmap, metrics, demo script, pitch deck |
| [Những gì đã gỡ và chưa làm](KNOWN-GAPS.md) | Bản ghi trung thực: tính năng đã gỡ, việc chưa xong, lỗi đã sửa |

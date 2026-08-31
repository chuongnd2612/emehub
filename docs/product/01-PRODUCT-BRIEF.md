# 1.1 Product Brief — EmeHub

**Đội:** `CLGT-EAM` · **Thành viên:** Nguyễn Đình Chương · Đào Văn Linh · Đồng Huỳnh Giao

---

## Product Overview

**EmeHub** là identity provider và configuration store dùng chung cho bộ agent AI nội bộ của
EMESOFT. Hub sở hữu user, session, credential, provider connection, project, repository và
knowledge base. Agent — ứng dụng làm việc chuyên môn cho một discipline — authenticate bằng
token do hub cấp và đọc cấu hình xuống từ hub qua HTTP.

Hôm nay suite gồm hai ứng dụng đang chạy:

| Ứng dụng | Vai trò |
|---|---|
| **EmeHub** | Hub — identity, credential, project, knowledge base. Không làm việc chuyên môn |
| **Q-Agent** | Agent cho QC/QA — từ ticket Azure DevOps ra test case đã duyệt, spec Playwright đã chạy, evidence và comment trả về ticket |

D-Agent (DEV) và B-Agent (BA) là **ví dụ về agent tương lai**: chúng plug vào qua cùng một
contract mà không phải sửa hub. Đây là điểm kiểm chứng của thiết kế, không phải ứng dụng đang chạy.

Hub tự đặt một boundary hẹp và ghi rõ: **hub chỉ build artefact mà nó đã sở hữu toàn bộ input** —
hôm nay là knowledge base, và không gì khác. Hub không sinh test, không sinh code, không drive
browser, không tạo pull request.

## Problem Statement

Hai lớp vấn đề, giải theo đúng thứ tự.

**Lớp 1 — công việc lặp quanh mỗi ticket.** QC/QA đọc requirement, gõ lại thành test case, nhập
từng case vào Azure DevOps, viết spec Playwright, chạy, thu evidence, comment kết quả về ticket.
Phần cần chuyên môn — case đã đủ chưa, risk nằm ở đâu — bị dồn vào thời gian còn thừa.

**Lớp 2 — tool AI nội bộ không có nơi quản lý.** Mỗi tool tự giữ user, PAT Azure DevOps, Claude
credential, cấu hình project. Cùng một thông tin khai lại ở từng nơi; không ai biết ai đang dùng
tool gì với quyền gì; một người nghỉ việc phải thu hồi ở nhiều chỗ.

## Target Users

| User | Dùng gì | Quan tâm gì |
|---|---|---|
| **QC/QA engineer** | Q-Agent + project/knowledge trên hub | Test coverage, spec chạy được, evidence đầy đủ |
| **Admin / Tech lead** | EmeHub | Credential tập trung, phân quyền, audit, chi phí Claude |
| **DEV, BA** *(giai đoạn sau)* | Agent tương lai trên cùng hub | Không phải khai lại cấu hình đã có |

## User Pain Points

1. **Gõ lại chiếm phần lớn thời gian.** Test case → Azure DevOps → spec là ba lần diễn đạt lại
   cùng một requirement.
2. **Bảo trì automation tốn hơn viết mới.** UI đổi một selector là một loạt spec đỏ.
3. **AI sinh code không dùng được vì đoán selector.** Model suy selector từ ngữ cảnh nó thấy; code
   trông hợp lý nhưng fail lúc chạy.
4. **Không có chuẩn khi dùng AI.** Ai cũng tự mở chat và tự viết prompt. Chất lượng phụ thuộc kỹ
   năng viết prompt chứ không phụ thuộc chuyên môn QA, và kinh nghiệm không tích luỹ thành tài sản
   nhóm.
5. **Credential phân mảnh.** Claude account dùng chung thì xếp hàng sau rate limit và không ai biết
   mình tiêu bao nhiêu; PAT nằm rải ở từng tool.

## Solution

**Một hub, nhiều agent, một contract.**

- Hub giữ identity (user, role, 2FA, session), credential (Claude, provider PAT), project
  (base URL, environment, test account, repository) và knowledge base về source code.
- Agent authenticate bằng **audience-scoped JWT** do hub ký, validate local, không call ngược hub
  theo từng request. Revoke một session ở hub là logout device đó khỏi mọi agent.
- **Knowledge base build một lần trên hub, mọi agent cùng dùng.** Hub clone repo, chạy skill
  `project-bootstrap` qua Claude CLI trên source thật, rút ra stack, kiến trúc, route thật,
  selector thật, page object, fixture, auth flow.
- **Q-Agent chạy pipeline 7 bước** trên input đó, với một human approval gate bắt buộc ở giữa.
- **Live-harness authoring:** agent drive browser thật trước, emit spec sau — selector được ghi từ
  DOM thật thay vì suy đoán.

## Value Proposition

> Khai báo một lần ở hub. AI làm việc trên source thật của chính project. Người ký duyệt ở đúng
> ba chỗ đáng ký. Agent thêm vào không phải dựng lại nền tảng.

## Key Features

| # | Feature | Mô tả ngắn |
|---|---|---|
| 1 | Identity + SSO cho cả suite | Login một lần, audience-scoped token, revoke session là logout toàn suite |
| 2 | Claude credential hai lớp | `own → shared → none`; refresh token ghi ngược về hub; usage/cost per-user |
| 3 | Provider connection credential-first | Dán PAT trước, hệ thống tự liệt kê organisation và project; test được trên bản nháp |
| 4 | Project & Repository registry | Base URL, environment, test account (encrypted), binding tới provider |
| 5 | Knowledge base build trên hub | `project-bootstrap` trên source thật; `not_indexed → indexing → indexed → stale`; clone được từ shared namespace |
| 6 | Q-Agent pipeline 7 bước | Analyze → Review → Link → Automation → Execution → Evidence → Publish |
| 7 | Live-harness spec authoring | Chạy thật trước, emit spec sau; selector từ accessibility tree |
| 8 | Local Agent | Spec chạy trên máy tester; browser session không rời device |
| 9 | Audit log append-only | Category, actor, action, target, IP, status, run code |

## Why Now

- **Claude Code CLI đã đủ tin cậy để chạy headless trong pipeline**, có streaming, tool use và
  skill — không còn phải tự dựng agent loop.
- **Đội đã có hai công cụ AI chạy thật** trước khi có hub. Vấn đề phân mảnh credential/cấu hình là
  vấn đề quan sát được, không phải giả định.
- **Chi phí LLM đã đủ thấp** để chạy nhiều pass (analyze, generate, review, heal) trên một ticket
  mà vẫn rẻ hơn giờ công.

## Why AI

Ba việc trong pipeline không có lời giải deterministic:

1. **Đọc requirement bằng ngôn ngữ tự nhiên và suy ra test case có truy vết tới từng acceptance
   criteria.** Rule engine không làm được vì requirement không có schema.
2. **Đọc một codebase lạ và rút ra route, selector, page object dùng lại được.** Static analysis
   cho được AST, không cho được ngữ nghĩa "đây là màn hình login".
3. **Đọc một failure log kèm DOM và phân loại `test_defect` / `product_defect` / `flaky` /
   `environment` / `timeout`, rồi sửa có mục tiêu.**

Phần còn lại — CRUD, encrypt, JWT, phân quyền, gọi Azure DevOps API — cố tình **không** dùng AI.

## Expected Impact

| Trục | Kỳ vọng |
|---|---|
| Thời gian | Phần gõ lại của một ticket QA chuyển từ giờ sang phút thao tác; người chỉ còn duyệt ở Review Center |
| Chất lượng | Spec sinh từ DOM thật chạy green ngay, không cần heal pass; coverage truy vết được tới AC |
| Chuẩn hoá | 14 skill đi kèm sản phẩm — cùng một ticket, ai chạy cũng ra kết quả tương đương |
| Bảo mật | PAT không rời hub; Claude credential phát ra qua grant scope theo run, chỉ reach được 3 route |
| Mở rộng | Agent thứ ba onboard bằng cách đọc contract, không phải dựng lại identity/credential/knowledge |

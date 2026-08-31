# EmeHub — Bộ tài liệu dự thi AI Hackathon

**Đội:** CLGT-EAM · **Thành viên:** Nguyễn Đình Chương · Đào Văn Linh · Đồng Huỳnh Giao
**Sản phẩm:** EmeHub — identity provider và configuration store cho bộ agent AI nội bộ EMESOFT
**Truy cập:** `https://hub.chuongnd.click` · Q-Agent: `https://hub.chuongnd.click/qagent/`
**Source code:** [`chuongnd2612/emehub`](https://github.com/chuongnd2612/emehub) ·
[`chuongnd2612/q-agent`](https://github.com/chuongnd2612/q-agent) — cả hai public, branch `master`

Bộ tài liệu này **standalone** — đọc từ đầu tới cuối là đủ, không cần đọc tài liệu kỹ thuật nào
khác trong repo.

---

## 1. Product Definition

| Tài liệu | Nội dung |
|---|---|
| [01-PRODUCT-BRIEF.md](01-PRODUCT-BRIEF.md) | Product Overview · Problem Statement · Target Users · User Pain Points · Solution · Value Proposition · Key Features · Why Now · Why AI · Expected Impact |
| [02-USER-PROBLEM.md](02-USER-PROBLEM.md) | User Persona · Current User Journey · Pain Points · Jobs To Be Done · Current-State Flow · Future-State Flow |

## 2. Product Requirements

| Tài liệu | Nội dung |
|---|---|
| [03-PRD.md](03-PRD.md) | Product Goals · Scope · Functional / Non-Functional Requirements · User Stories · Acceptance Criteria · Out of Scope · Dependencies · Risks |
| [04-USER-FLOW.md](04-USER-FLOW.md) | Entry Point · User Actions · System Responses · AI Interactions · Decision Points · Success / Failure Paths · End State |

## 3. AI & Technical

| Tài liệu | Nội dung |
|---|---|
| [05-AI-SOLUTION.md](05-AI-SOLUTION.md) | AI Use Cases · Capabilities · Input/Output · AI & Agent Workflow · Context/Prompt Strategy · Tool Usage · Human-in-the-Loop · Guardrails · AI Failure Scenarios · Why AI Is Necessary |
| [06-ARCHITECTURE.md](06-ARCHITECTURE.md) | Architecture Overview · Frontend · Backend · AI/LLM Components · Agent/RAG/Tooling · Database · External Services · Data Flow · Integration Points · Security & Privacy |
| [07-AI-EVALUATION.md](07-AI-EVALUATION.md) | Methodology · Scenarios · Dataset · Metrics · Results · Failure Cases · Limitations · Before/After |

## 4. Product Management

| Tài liệu | Nội dung |
|---|---|
| [08-ROADMAP.md](08-ROADMAP.md) | Current State · Hackathon Scope · Next Priorities · Production Vision · Future Opportunities |
| [09-SUCCESS-METRICS.md](09-SUCCESS-METRICS.md) | Product / User / AI Metrics · Productivity Impact · Time Saved · Cost Reduction · Quality Improvement · Adoption |

## 5. Hackathon Submission

| Tài liệu | Nội dung |
|---|---|
| [10-DEMO-SCRIPT.md](10-DEMO-SCRIPT.md) | Kịch bản demo 8 phút theo 8 nhịp, kèm phương án dự phòng |
| [11-PITCH-DECK.md](11-PITCH-DECK.md) | 10 slide, nội dung slide + lời thoại + phụ lục Q&A |

## Kèm theo

| Tài liệu | Nội dung |
|---|---|
| [../SELLING-POINTS.md](../SELLING-POINTS.md) | Điểm nổi bật kỹ thuật, mỗi khẳng định dẫn tới file hoặc ADR trong repo |
| [../ACCOUNT.md](../ACCOUNT.md) | Link truy cập và tài khoản demo |

---

## Đọc theo thời gian có

| Có bao nhiêu phút | Đọc gì |
|---|---|
| **3 phút** | [01-PRODUCT-BRIEF.md](01-PRODUCT-BRIEF.md) |
| **10 phút** | 01 → [11-PITCH-DECK.md](11-PITCH-DECK.md) → [../SELLING-POINTS.md](../SELLING-POINTS.md) |
| **30 phút** | 01 → 02 → 05 → 06 → 07 |
| **Đầy đủ** | 01 → 11 theo thứ tự |

---

## Ba điều nói thẳng

Để người đọc không phải tự tìm ra:

1. **Hôm nay có hai ứng dụng chạy:** EmeHub và Q-Agent. D-Agent và B-Agent là **ví dụ kiểm chứng
   contract**, không phải ứng dụng thứ ba đang chạy.
2. **Cutover chưa xong.** Q-Agent mới tiêu thụ identity từ hub; credential và project vẫn còn bản
   của agent. Chi tiết ở [08-ROADMAP.md](08-ROADMAP.md).
3. **Số hiệu quả chưa đo có kiểm soát.** Cơ chế đo nằm sẵn trong sản phẩm, nhưng cỡ mẫu ticket còn
   nhỏ nên đội không quy thành phần trăm. Ô `[…]` trong tài liệu là chỗ chờ số đo thật. Chi tiết ở
   [07-AI-EVALUATION.md](07-AI-EVALUATION.md).

# 4.1 Product Roadmap

Nguyên tắc xuyên suốt: **mỗi phase kết thúc là cả suite vẫn chạy được.** Không có phase nào để hệ
thống ở trạng thái nửa migrate.

---

## Current State

**Đã chạy được.**

| Hạng mục | Trạng thái |
|---|---|
| EmeHub — FastAPI + Postgres sau nginx, 11 view trên endpoint thật, 788 hàm test | ✅ |
| Identity: login, 2FA, session, user management, audit log | ✅ |
| Claude credential: personal/shared, resolve `own → shared → none`, usage, refresh write-back | ✅ |
| Provider connection: Azure DevOps / GitHub / Jira, credential-first, capability binding | ✅ |
| Project / repository / test account registry | ✅ |
| Knowledge base build **trên hub** qua `project-bootstrap` | ✅ |
| Ticket store + sync + filter phía server | ✅ |
| Q-Agent pipeline 7 bước trên dữ liệu thật, live-harness authoring, Local Agent | ✅ |
| Cả suite sau **một origin**, lên bằng một lệnh | ✅ |
| **SSO hand-off hub → Q-Agent** (Phase 2, gated `QAGENT_HUB_SSO_ENABLED`) | ✅ |

**Chưa xong — nói thẳng để không bị hiểu nhầm.**

Q-Agent mới tiêu thụ **identity** từ hub. Credential, project và knowledge base vẫn còn bản của
agent, nên hôm nay hub chạy **song song** với agent chứ chưa đứng trước nó. Đây là việc tiếp theo,
và là lý do phần nền tảng được xây trước.

| Còn tồn tại ở Q-Agent | Vì sao chưa gỡ |
|---|---|
| `/auth/*` và bảng `users` / `auth_sessions` riêng | Migration user toàn phần logout mọi người một lần — phải đặt lịch |
| `claude_credentials`, `provider_connections` riêng | Encrypted bằng key dẫn xuất từ `QAGENT_SECRET_KEY`; migration là **decrypt-cũ → encrypt-mới**, phải rehearse trên bản copy DB |

---

## Hackathon Scope

Phạm vi trình diễn của bản dự thi, đúng bằng những gì chạy được:

| Trong scope | Ghi chú |
|---|---|
| EmeHub đầy đủ: identity, credential, connection, project, repo, knowledge, ticket, audit | Chạy trên `hub.chuongnd.click` |
| Q-Agent: pipeline 7 bước, Review Center, live-harness, Local Agent | Chạy trên `hub.chuongnd.click/qagent/` |
| SSO hub → Q-Agent | Login một lần |
| Knowledge base build từ source thật + clone từ shared namespace | Build sẵn trước demo |
| Golden journey: một ticket Azure DevOps → test case đã duyệt → spec chạy green → evidence → comment về ticket | Nội dung demo |

| Ngoài scope | Lý do |
|---|---|
| D-Agent như ứng dụng thứ ba đang chạy | Là **ví dụ kiểm chứng contract**, không phải scope dự thi |
| Cutover credential/project của Q-Agent sang hub | Phase 3–4, cần migration có lịch |
| RS256 + JWKS | `kid` đã emit từ token đầu tiên nên đây là thay đổi cộng thêm, không breaking |
| Organisation entity thật | Đang dùng `owner_id` + shared namespace |
| Mobile layout, SSO với IdP ngoài | Chưa thiết kế / chưa lên lịch |

---

## Next Priorities

Theo thứ tự, mỗi mục có exit criteria kiểm chứng được.

### P1 — Hoàn tất cutover identity của Q-Agent
Gỡ `/auth/*`, `users`, `auth_sessions` của Q-Agent. Argon2 hash và TOTP secret portable nên user
giữ nguyên mật khẩu; session **không** migrate — cả đội logout một lần, vào giờ đã hẹn.
**Exit:** Q-Agent không còn authentication của riêng nó.

### P2 — Cutover credential
Một script one-shot **decrypt bằng `QAGENT_SECRET_KEY`, re-encrypt bằng `EMEHUB_ENCRYPTION_KEY`**,
idempotent, rehearse trên bản copy DB trước.
**Exit:** một Claude credential thêm ở hub được một run của Q-Agent dùng; bảng
`claude_credentials` và `provider_connections` của Q-Agent biến mất.

### P3 — Cutover project + knowledge
Q-Agent đọc project, environment, test account, repository và knowledge base từ hub.
**Exit:** project tạo ở hub hiện ra trong Q-Agent; knowledge base build một lần phục vụ mọi agent.

### P4 — Eval dataset đóng gói
Bộ ticket cố định + expected output, chạy lại sau mỗi thay đổi prompt/skill, để bắt regression
chất lượng AI như đang bắt regression code.
**Exit:** M1–M6 ở [07-AI-EVALUATION.md](07-AI-EVALUATION.md) có số chạy tự động mỗi PR.

### P5 — RS256 + JWKS
Bỏ shared secret giữa hub và agent. Additive, vì `kid` đã có sẵn.

---

## Production Vision

Trạng thái đích của giai đoạn hiện tại:

```
   Một login · một chỗ khai credential · một knowledge base
                          │
   ┌──────────────────────┼──────────────────────┐
   ▼                      ▼                      ▼
Q-Agent (QA)        D-Agent (DEV)          B-Agent (BA)
ticket → test       ticket → PR            requirement → spec
```

Ba điều kiện để gọi là production:

| Điều kiện | Kiểm chứng |
|---|---|
| Không agent nào còn authentication riêng | Bảng `users` chỉ tồn tại ở hub |
| Không agent nào còn bản sao credential | Bảng credential chỉ tồn tại ở hub |
| Agent thứ ba onboard **chỉ bằng cách đọc contract** | Không PR nào vào hub để thêm agent đó |

**D-Agent là phép thử của điều kiện thứ ba.** Hub side đã sẵn sàng cho nó: `dagent` là audience
đăng ký được, `/auth/agent-token` và `/auth/agent-grant` mint được cho nó, và
`GET /connections/{id}/secret` đóng nốt khoảng trống cuối cùng phía hub — hai case cần PAT trong
*process environment* (clone repo, MCP config) mà không endpoint hẹp nào cấp được. Mọi việc còn
lại nằm phía agent.

**Một câu hỏi phải trả lời trước, vì nó quyết định cả phase:** D-Agent ở lại là local developer
tool hay trở thành hosted service? Mô hình thực thi `--dangerously-skip-permissions` chấp nhận
được ở vế đầu và không chấp nhận được ở vế sau.

---

## Future Opportunities

Chưa lên lịch. Xếp theo mức độ đã sẵn nền:

| Cơ hội | Nền đã có | Còn thiếu |
|---|---|---|
| **B-Agent (BA)** — requirement → user story + AC chuẩn hoá | Identity, credential, project, ticket, KB | Skill riêng cho phân tích nghiệp vụ |
| **Cross-agent hand-off** — mang một ticket từ D-Agent sang Q-Agent bằng một click | Context đã chia sẻ sẵn nên rẻ | Một UI hand-off; là một mảnh việc riêng |
| **Claude account pool** — chia sẻ nhiều account có kiểm soát tiêu thụ | Usage đã ghi theo owner, credential đã hai lớp | Scheduler chọn account theo hạn mức còn lại |
| **SSO với IdP ngoài** (Entra, Google Workspace) | Hub thiết kế để trở thành OIDC client sau này | Chưa lên lịch; không có gì trong Phase 1–5 làm việc này khó hơn |
| **Agent khác của suite** — DataAgent, OpsAgent, DocAgent, SecAgent | Cùng contract | Từng bộ skill riêng |
| **Organisation / tenant entity thật** | `owner_id` + shared namespace | Migration trên mọi bảng có scope — chỉ làm khi có nhu cầu thật |
| **LLM-as-judge cho failure classification** | Failure class đã có 5 loại | Judge + bộ mẫu đã gán nhãn |

Điểm chung của mọi mục trên: **không mục nào đòi dựng lại identity, credential hay knowledge
base.** Đó chính là thứ hub được xây để đổi lấy.

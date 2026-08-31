# 3.2 AI / System Architecture

---

## Architecture Overview

Hai ứng dụng độc lập, hai repository riêng, tích hợp qua **HTTP + JWT do hub ký**, đứng sau
**một origin** duy nhất.

```
                        ┌──────────────────────────────────────────┐
   Browser ────────────►│  edge (nginx) — một origin cho cả suite  │
                        │  /          → EmeHub web                 │
                        │  /qagent/   → Q-Agent web                │
                        └───────┬───────────────────────┬──────────┘
                                │                       │
                ┌───────────────▼──────────┐   ┌────────▼─────────────────┐
                │  EmeHub                  │   │  Q-Agent                 │
                │  ├ web  React 19 + Vite  │   │  ├ web  React + Vite     │
                │  └ api  FastAPI (3.13)   │   │  └ api  FastAPI          │
                └───┬──────────────┬───────┘   └───┬──────────────┬───────┘
                    │              │               │              │
            ┌───────▼──────┐  ┌────▼─────────┐ ┌───▼──────┐  ┌────▼────────┐
            │ Postgres 16  │  │ workspace    │ │ Postgres │  │ Claude CLI  │
            │ emehub       │  │ volume       │ │ qagent   │  │ subprocess  │
            └──────────────┘  │ knowledge/   │ └──────────┘  └─────────────┘
                              │ repos/       │                      │
                              │ auth/        │              ┌───────▼───────┐
                              └──────┬───────┘              │ browser-      │
                                     │                      │ harness       │
                              ┌──────▼───────┐              └───────────────┘
                              │ Claude CLI   │
                              │ subprocess   │  ← chỉ để build knowledge
                              └──────────────┘

   Local Agent (máy tester, Node) ──── device token ────► Q-Agent api
   Azure DevOps / GitHub / Jira ◄──── proxy qua hub ────  EmeHub api
   Anthropic API ◄──────────────────── Claude CLI
```

**Nguyên tắc chia trách nhiệm:** hub sở hữu identity và shared config; agent sở hữu domain work.
Hub chỉ build artefact mà nó đã sở hữu toàn bộ input — hôm nay là knowledge base, và không gì khác.

---

## Frontend

| | |
|---|---|
| **Stack** | React 19, Vite, TypeScript, Tailwind 4 |
| **Quy mô** | 11 view chạy trên endpoint thật: Landing, Overview, Projects & Repositories, Tickets, Import dialog, Claude Settings, Authentication, User Management, Integrations, Settings, overlays |
| **Design token** | CSS custom properties (`--bg`, `--panel`, `--card*`, `--bd*`, `--txt*`, `--p*`, …). Light mode bắt buộc, 4 accent, mặc định EMESOFT Red `#e1172b`. Không có hex trần trong component |
| **Navigation** | **URL là source of truth**; Zustand chỉ giữ UI-only state (modal, filter, draft) |
| **Overlay** | Portal ra `document.body` + fixed positioning theo bounding rect của trigger — tránh stacking-context trap từ `backdrop-filter` / `transform` |
| **Realtime** | Poll cho trạng thái build knowledge (`indexing`); stream log cho run ở Q-Agent |
| **Data layer** | `app/src/data/` — tầng typed. Endpoint chưa có thì stub sau tầng này, không bịa route ngầm |
| **Gate** | `tsc -b --noEmit` + `vite build`. Không có unit-test harness; verify runtime bằng Playwright |

---

## Backend

| | |
|---|---|
| **Stack** | FastAPI, Python 3.13, uv, SQLAlchemy 2, Alembic |
| **Quy mô** | 14 router module, 788 hàm test |
| **Router chính** | `auth`, `me`, `agents`, `agent_open`, `credentials`, `connections`, `projects`, `tickets`, `saved_queries`, `preferences`, `audit`, `health` |
| **Auth** | Argon2 password hash, TOTP 2FA, refresh token HttpOnly cookie (chỉ lưu hash), access token audience-scoped mang `sub`/`sid`/`aud`/`kid` |
| **Background work** | Build knowledge chạy nền, bounded bởi `EMEHUB_KNOWLEDGE_BUILD_CONCURRENCY` (mặc định 2). `indexing` vừa là in-flight guard vừa là thứ UI poll |
| **Migration** | Alembic cho mọi schema change — không có auto-create |

**Boundary được cưỡng chế bằng type, không bằng quy ước:** `resolve_material` trong
`api/app/services/claude_credentials.py` là hàm **duy nhất** trả credential material. Mọi endpoint
khác khai `response_model` không có trường nào chứa được nó — một lỗi trong handler cũng không
serialise nổi token ra response.

---

## AI / LLM Components

| Thành phần | Chạy ở | Vai trò |
|---|---|---|
| **Claude Code CLI** (`@anthropic-ai/claude-code`) | Subprocess do backend spawn, cả hub và agent | Toàn bộ inference. Không có SDK call trực tiếp |
| **Skill** (`SKILL.md`) | Hub: 1 (`project-bootstrap`). Q-Agent: 14 | Methodology + quality rule + output template, inject làm **system prompt** cho đúng action đó |
| **`browser-harness` CLI** | Phía có browser (Local Agent / host có Chrome) | Cho agent drive Chrome thật: accessibility tree, dispatch event trên selector, verify hiệu ứng |
| **MCP Azure DevOps** | Cấu hình cho từng run | Cho agent đọc work item liên quan |

**Image API cố tình mang `git`, Node 20 và Claude Code CLI — nhưng không mang Chromium.** Hub
build knowledge (đọc source), hub không drive browser. Ranh giới đó là kiến trúc, không phải thiếu sót.

---

## Agent / RAG / Tooling

Không dùng vector store và không dùng RAG theo nghĩa embedding + similarity search. Grounding đi
theo đường khác, và có chủ đích:

| | RAG thường | Cách làm ở đây |
|---|---|---|
| Nguồn | Chunk source code + embedding | `project-bootstrap` **đọc toàn bộ source** và chưng cất thành `knowledge.json` có cấu trúc |
| Truy xuất | Similarity search top-k | Agent nhận `knowledge.json` trực tiếp, đọc thêm file cụ thể qua file tool khi cần |
| Vì sao | — | Câu hỏi ở đây không phải "đoạn code nào giống câu hỏi này" mà "route và selector của project này là gì" — một fact table nhỏ trả lời tốt hơn top-k chunk |

**Vòng làm giàu:** selector verify được trên app đang chạy được `PATCH` ngược về hub với timestamp
và strategy đã hoạt động. Entry `verified_at_runtime` **thắng** entry suy ra từ source; merge sau
không ghi đè nó.

**Tool surface của agent:** file read/write/glob/grep (giới hạn trong workspace theo owner), shell
(`git`, `npx playwright`, `npm`), `browser-harness`, MCP Azure DevOps.

---

## Database

**PostgreSQL 16**, mỗi ứng dụng một database riêng. Bảng chính của hub:

| Nhóm | Bảng | Ghi chú |
|---|---|---|
| Identity | `users`, `sessions` | `totp_secret`, refresh token lưu **hash** |
| Credential | `claude_credentials`, `claude_usage` | Credential encrypted at rest; `has_refresh_token` là **boolean**, không lưu token |
| Provider | `provider_connections` | PAT encrypted; capability `work_item` / `repository` |
| Work | `projects`, `project_config`, `repositories`, `project_knowledge`, `tickets` | Test-account password encrypted |
| Vận hành | `audit_log`, `agent_devices`, `saved_queries`, `preferences` | Audit append-only |

**Multi-tenancy:** chưa có organisation entity. Dùng `owner_id` nullable trên mọi bảng có scope;
`NULL` là **shared namespace**. Chọn như vậy để migration từ Q-Agent sau này là một lần copy row
chứ không phải backfill.

**Artefact trên đĩa** (volume `emehub-workspace`, scope theo owner): `knowledge/`, `repos/`,
`auth/`. Volume này giữ credential đã materialise trong lúc build nên được coi là **sensitive**.

---

## External Services

| Service | Dùng để | Secret đi đâu |
|---|---|---|
| **Anthropic API** | Inference (qua Claude CLI) | Credential materialise xuống disk trong thời gian chạy CLI, qua `CLAUDE_SECURESTORAGE_CONFIG_DIR` |
| **Azure DevOps** | Work item, repository, test case | PAT **ở lại hub**; hub proxy call. Ngoại lệ: `GET /connections/{id}/secret` cho clone repo và MCP config |
| **GitHub / Jira** | Adapter tương đương | Như trên |

Ngoài Anthropic API, **không có dữ liệu nào rời khỏi hạ tầng nội bộ**.

---

## Data Flow

### DF-1 Đăng nhập và hand-off sang agent

```
Browser ──login──► Hub api ──► Postgres (verify Argon2 + TOTP)
        ◄─ refresh cookie HttpOnly (chỉ hash lưu DB) ─┘
Browser ──POST /auth/agent-token──► Hub api ──► access token {sub, sid, aud=qagent, kid}
        (KHÔNG rotate refresh token — hai SPA dùng chung credential xoay sẽ đá nhau ra)
Browser ──token──► Q-Agent api ──validate LOCAL (không call ngược hub)──► session của agent
```

Revoke một session ở hub → mọi token mang `sid` đó thành invalid → device logout khỏi mọi agent.

### DF-2 Build knowledge base

```
UI ──POST /projects/{key}/repos/{repo}/knowledge/build──► Hub api
   status = indexing (in-flight guard + thứ UI poll)
   ├─ decrypt PAT ──► git clone vào workspace/{owner}/repos/
   ├─ resolve_material() ──► materialise Claude credential vào thư mục khoá
   ├─ spawn Claude CLI với skill project-bootstrap ──► Anthropic API
   ├─ ghi knowledge.md + knowledge.json ──► workspace/{owner}/knowledge/
   ├─ POST /credentials/claude/usage  (token + cost, attribute theo owner)
   └─ status = indexed | error (kèm lastError)
```

### DF-3 Một run của Q-Agent

```
Q-Agent ──GET /tickets──► Hub (proxy Azure DevOps bằng PAT của hub)
Q-Agent ──POST /auth/agent-grant──► Hub  (run-scoped grant: access token 15' không đủ cho run nền)
   grant chỉ reach được: GET /credentials/claude/resolve
                         PUT /credentials/claude/refreshed
                         POST /credentials/claude/usage
Q-Agent ──GET knowledge──► Hub ──► knowledge.json
Q-Agent ──spawn Claude CLI──► test case (pending)
                       ══► GATE 1: người duyệt
Q-Agent ──POST test case──► Hub ──proxy──► Azure DevOps      (GATE 2: local mode?)
Q-Agent ──browser-harness──► app thật ──► spec Playwright
Q-Agent ──execution──► Local Agent (nếu app cần đăng nhập thật)
   Local Agent trả về: spec result + evidence.  Cookie/storageState KHÔNG rời máy tester.
Q-Agent ──PATCH knowledge──► Hub  (selector verified-at-runtime)
Q-Agent ──comment──► Hub ──proxy──► Azure DevOps             (GATE 3: preview)
```

---

## Integration Points

| Điểm | Hướng | Contract |
|---|---|---|
| `POST /auth/agent-token` | Browser → Hub | Đổi refresh cookie lấy agent token, **không rotate** |
| `POST /auth/agent-grant` | Agent → Hub | Run-scoped grant cho background run |
| `GET /agents` | Browser → Hub | Launch registry; phân biệt `registered` và `handoffReady` |
| `GET /credentials/claude/resolve` | Agent → Hub | Endpoint **duy nhất** trả Claude credential material |
| `PUT /credentials/claude/refreshed` | Agent → Hub | Ghi lại token CLI đã tự renew |
| `POST /credentials/claude/usage` | Agent → Hub | Token + cost của một call đã xong |
| `GET /connections/{id}/secret` | Agent → Hub | Endpoint **duy nhất** trả PAT, chỉ cho agent audience |
| `GET/PATCH/PUT .../knowledge` | Agent ↔ Hub | Đọc KB; ghi ngược entry verified-at-runtime |
| `GET /projects`, `/tickets` | Agent → Hub | Cấu hình và ticket đã normalise |

Contract được ghi thành tài liệu thật (`docs/INTEGRATION.md`). Đổi contract thì phải update nó
trong cùng PR và mở issue ở repo agent tương ứng.

---

## Security / Privacy Considerations

**Ba loại secret, ba boundary, mỗi loại một cơ chế cưỡng chế riêng.**

### 1. Provider PAT — không rời hub
Encrypted at rest, hub proxy mọi provider call. `GET /connections` trả `hasPat: true`. Generic
forwarder `POST /connections/{id}/proxy` bị **bỏ hẳn**, không hoãn — nó là bề mặt SSRF và
header-leak; endpoint hẹp theo từng operation phủ đủ.

### 2. Claude credential — ngoại lệ duy nhất, và nó bị thu hẹp
Claude CLI cần credential trên disk. Hai cơ chế giới hạn thiệt hại:

- **Biến môi trường hẹp:** `CLAUDE_SECURESTORAGE_CONFIG_DIR` chỉ relocate đúng file credential,
  không phải `CLAUDE_CONFIG_DIR` vốn kéo theo `skills/`, `settings.json`, `projects/`.
- **Run-scoped grant:** grant gắn với đúng một run, chết cùng hub session, không tự renew, và chỉ
  reach được **ba route**. Giới hạn này cưỡng chế **bằng wiring** — không route nào khác depend
  `require_credential_grant`, và audience của grant không bao giờ registerable nên
  `require_principal` và `require_user` đều reject nó. Thêm route mới không vô tình mở rộng phạm vi.

### 3. Browser session của tester — không rời máy tester
Local Agent chạy spec tại chỗ; cookie và `storageState` ở lại device. Device chứng minh identity
qua pairing code ngắn hạn → token per-device tại `~/.qagent-agent/config.json`; server chỉ giữ
**hash** trên row `AgentDevice`. Job scope theo device owner; token revoke được từ app.

### Nền tảng

| Quy tắc | Cưỡng chế |
|---|---|
| `EMEHUB_JWT_SECRET` và `EMEHUB_ENCRYPTION_KEY` là hai secret riêng | ADR 0005. Không dẫn xuất từ nhau |
| Thiếu secret → **refuse to start** | Không sinh key lúc boot — key sinh lúc boot tạo ra row không decrypt được sau restart |
| **Không fail-open** | Không có `authDisabled()` nào trong hub. Đọc lỗi product availability nghĩa là **đóng** |
| Không log, không trả secret | `response_model` không có trường nào chứa được |
| Secret ngoài git | Chỉ `.env.example` được track |
| Audit | Append-only: category, actor + actor type, action, target, IP, status, run code |

**Privacy:** toàn bộ self-hosted. Source code, ticket, test account, evidence nằm trong hạ tầng
nội bộ. Dữ liệu ra ngoài duy nhất là nội dung gửi tới Anthropic API trong lúc chạy Claude CLI.

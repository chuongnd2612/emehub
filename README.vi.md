# EmeHub

> Một workspace cho mọi agent của EMESOFT.

*[English version](README.md)*

---

## Dùng thử ngay

Hai ứng dụng nằm sau một origin. Bắt đầu từ EmeHub — đăng nhập một lần dùng được cả hai.

| Ứng dụng | Đường dẫn |
|---|---|
| **EmeHub** — hub: identity, credential, project | <https://hub.chuongnd.click> |
| **Q-Agent** — agent cho QC/QA | <https://hub.chuongnd.click/qagent/> |

**Tài khoản demo**

| Role | Username | Password |
|---|---|---|
| Admin | `hub.admin@emesoft.net` | `010203x@X` |

**Đội `CLGT-EAM`** — Nguyễn Đình Chương · Đào Văn Linh · Đồng Huỳnh Giao

> [Hướng dẫn sử dụng](docs/USER-GUIDE.md) đi từ màn đăng nhập tới lúc kết quả execution quay về
> ticket.

---

## Đây là gì

EmeHub là **source of truth** cho mọi thứ suite dùng chung: identity, Claude credential, provider
connection, project, repository và knowledge base.

Agent thôi tự giữ những thứ đó và đọc chúng từ hub qua HTTP, xác thực bằng token do hub mint. Hôm
nay agent đó là **Q-Agent** (QA). Hub cũng là cửa trước: đăng nhập một lần, thấy cả suite, launch
agent.

**Hub được thiết kế cho nhiều agent, không chỉ một.** Contract — token claim, config endpoint,
degradation behaviour — là một document riêng ([INTEGRATION.md](docs/INTEGRATION.md)), nên một agent
mới plug vào bằng cách implement contract đó chứ không phải bằng cách sửa hub. **D-Agent** (dev) và
**B-Agent** (BA) là hai ví dụ đang trên đường đi theo lối này.

```
                    ┌─────────────────────────────┐
                    │           EmeHub            │
                    │  identity · user · role     │
                    │  Claude credential          │
                    │  provider connection        │
                    │  project · knowledge        │
                    │  ticket · audit             │
                    └──────┬───────────────┬──────┘
                  JWT +    │               │    JWT +
                  config   │               │    config
                    ┌──────┴──────┐ ┌──────┴───────┐
                    │   Q-Agent   │ │  agent kế    │
                    │ run · spec  │ │  tiếp        │
                    │ evidence    │ │  (D-Agent,   │
                    │ execution   │ │   B-Agent…)  │
                    └─────────────┘ └──────────────┘
                         hôm nay        cùng contract
```

**Boundary của hub được giữ chặt:** hub chỉ build những artefact mà nó đã sở hữu toàn bộ input —
hôm nay là knowledge base, và không gì khác. Hub **không** sinh test, không sinh code, không drive
browser, không tạo PR. Đó là việc của agent.

---

## Ba điểm khác biệt

Đầy đủ ở [SELLING-POINTS.md](docs/SELLING-POINTS.md).

**Claude credential có hai lớp.** Mỗi user một credential riêng, cộng một credential shared ở
scope workspace do admin publish; resolve theo `own → shared → none` và đổi mode tức thì. Usage và
rate limit hiển thị per-user.

**Spec sinh từ DOM thật.** Q-Agent drive browser thật trước, emit spec sau: thực thi từng step
trên app đang chạy, resolve selector qua accessibility tree, verify chính selector sắp emit — rồi
mới sinh file Playwright. Không có selector suy đoán.

**Ba loại secret, ba boundary.** Provider PAT không rời khỏi hub — hub proxy mọi provider call.
`storageState` của tester không rời khỏi device — Local Agent execute tại chỗ. Claude credential
là exception duy nhất, và bị thu hẹp bằng run-scoped grant chỉ reach được ba route.

---

## Đọc theo thứ tự nào

| Tài liệu | Dành cho |
|---|---|
| [docs/ACCOUNT.md](docs/ACCOUNT.md) | Link truy cập và tài khoản demo |
| [docs/USER-GUIDE.md](docs/USER-GUIDE.md) | **Bắt đầu ở đây** — dùng sản phẩm, đầu tới cuối |
| [docs/SELLING-POINTS.md](docs/SELLING-POINTS.md) | Kiến trúc và điểm khác biệt |
| [docs/CONTEXT.md](docs/CONTEXT.md) | Vocabulary dùng chung |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | Hợp đồng giữa hub và agent |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Đang ở phase nào, còn gì phía trước |
| [docs/adr/](docs/adr/) | Các quyết định kiến trúc và lý do |

---

## Chạy tại máy

Chỉ riêng hub, không kèm agent:

```bash
cp .env.example .env
```

Sinh **hai secret** — chúng phải là **hai giá trị khác nhau**
([ADR 0005](docs/adr/0005-secret-and-key-management.md)). API **refuse to start** nếu thiếu một trong
hai; không có fallback tự sinh, vì một encryption key sinh lúc boot sẽ tạo ra dữ liệu không
decrypt được sau restart kế tiếp.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> EMEHUB_JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> EMEHUB_ENCRYPTION_KEY

docker compose up -d --build
```

- Giao diện hub — <http://localhost:5180>
- Health — <http://localhost:5180/api/health>

Cổng (web 5180, api 8790, db 5457) chọn để không đụng với Q-Agent, nên chạy song song hai stack
trên một máy được.

**Lần `--build` đầu tiên mất vài phút.** Từ [ADR 0007](docs/adr/0007-knowledge-builds-run-on-the-hub.md),
hub tự build knowledge base, nên image API cài thêm `git`, Node 20 và `@anthropic-ai/claude-code`
lên trên nền Python. (Không có chromium — hub không chạy browser.)

```bash
docker compose exec api sh -c 'git --version && node --version && claude --version'
```

### Hai thứ phải tự cung cấp

Thiếu chúng thì knowledge build dừng ở status `error` kèm thông báo thiếu cái gì — nó **không**
fail request:

- **Một Claude credential** — upload ở *Claude Settings*, hoặc dùng shared credential do admin
  publish.
- **Một repository connection kèm PAT** — ở *Integrations*, bind vào project có repo cần clone.

> Volume `emehub-workspace` chứa repository clone và — trong thời gian build — một Claude
> credential đã decrypt. Không mount world-readable, không copy tuỳ tiện.

### Chạy cả suite

`suite.sh` / `suite.ps1` bọc `docker compose -f docker-compose.suite.yml`, truyền vào `.env` của
cả ba repo. Không bao giờ chạy đồng thời hai cách — cùng port, khác volume.

---

## Đóng góp

Convention, architectural boundary và workflow nằm ở [CLAUDE.md](CLAUDE.md). Branch mặc định là
`master`.

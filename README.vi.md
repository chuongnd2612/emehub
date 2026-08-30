# EmeHub

> Một workspace cho mọi agent của EMESOFT.

*[English version](README.md)*

---

## Dùng thử ngay

Ba ứng dụng nằm sau **một địa chỉ duy nhất**. Bắt đầu từ EmeHub — đăng nhập một lần là dùng được
cả ba, không phải đăng nhập lại khi chuyển sang agent.

| Ứng dụng | Đường dẫn |
|---|---|
| **EmeHub** — hub: danh tính, credential, project | <https://hub.chuongnd.click> |
| **Q-Agent** — agent cho QC/QA | <https://hub.chuongnd.click/qagent/> |
| **D-Agent** — agent cho DEV | <https://hub.chuongnd.click/dagent> |

**Tài khoản demo**

| Role | Username | Password |
|---|---|---|
| Admin | `hub.admin@emesoft.net` | `010203x@X` |

**Đội `CLGT-EAM`** — Nguyễn Đình Chương · Đào Văn Linh · Đồng Huỳnh Giao

> Vào thẳng [Hướng dẫn sử dụng](docs/USER-GUIDE.md) nếu muốn có người dẫn đường từ màn đăng nhập
> tới lúc kết quả test quay về ticket.

---

## Đây là gì

EmeHub là **nguồn sự thật** cho mọi thứ mà bộ agent EMESOFT dùng chung: bạn là ai, bạn chạy bằng
tài khoản Claude nào, đang kết nối tới tổ chức Azure DevOps / GitHub / Jira nào, có những project
và repository nào, và hệ thống biết gì về chúng.

Các agent chuyên biệt — **Q-Agent** cho QA, **D-Agent** cho phát triển — thôi tự giữ những thứ đó
và đọc chúng từ hub qua HTTP, xác thực bằng token do hub cấp.

Hub cũng là cửa trước: đăng nhập một lần, thấy cả suite, mở agent.

```
                    ┌─────────────────────────────┐
                    │           EmeHub            │
                    │  danh tính · người dùng     │
                    │  credential Claude          │
                    │  kết nối provider           │
                    │  project · knowledge        │
                    │  ticket · audit             │
                    └──────┬───────────────┬──────┘
                  JWT +    │               │    JWT +
                  cấu hình │               │    cấu hình
                    ┌──────┴──────┐ ┌──────┴──────┐
                    │   Q-Agent   │ │   D-Agent   │
                    │ run · spec  │ │ execution   │
                    │ evidence    │ │ worktree    │
                    │ execution   │ │ skill       │
                    └─────────────┘ └─────────────┘
```

**Ranh giới của hub được giữ chặt:** hub chỉ dựng những artefact mà nó đã sở hữu toàn bộ đầu vào —
hôm nay là knowledge base, và không gì khác. Hub **không** sinh test, không sinh code, không lái
trình duyệt, không tạo PR. Việc đó là việc của agent.

---

## Vì sao đáng xem

Bốn điều làm suite này khác. Đầy đủ ở [SELLING-POINTS.md](docs/SELLING-POINTS.md).

**Một tài khoản Claude không còn là nút thắt cổ chai.** Mỗi người có credential riêng, admin
publish thêm một credential dùng chung ở cấp workspace, và công tắc đổi qua lại tức thì theo quy
tắc `own → shared → none`. Người mới chạy được từ phút đầu; ai có tài khoản riêng thì tự thấy chi
tiêu của mình.

**Spec test được viết từ DOM thật.** Q-Agent lái trình duyệt thật trước, viết spec sau: thực hiện
từng bước trên app đang chạy, đọc selector thật trên DOM thật, tự tạo dữ liệu test nếu thiếu — rồi
mới sinh file Playwright từ đúng những gì đã chạy được. Không có selector đoán mò.

**Bí mật nằm đúng chỗ.** PAT của provider không rời khỏi hub — hub tự proxy lời gọi. Cookie đăng
nhập của tester không rời khỏi máy tester — Local Agent chạy spec ngay tại đó. Credential Claude
đi ra ngoài đúng một lần, có văn bản quy định, và bị thu hẹp bằng grant chỉ với tới được ba route.

**Chúng tôi tự khai những gì chưa làm.** [KNOWN-GAPS.md](docs/KNOWN-GAPS.md) ghi thẳng tính năng
nào đã bị gỡ khỏi giao diện vì chưa thật, chỗ nào còn nợ, và cả những dòng tài liệu cũ mà chúng
tôi kiểm chứng lại rồi phát hiện là sai.

---

## Đọc theo thứ tự nào

| Tài liệu | Dành cho |
|---|---|
| [docs/ACCOUNT.md](docs/ACCOUNT.md) | Link truy cập và tài khoản demo |
| [docs/USER-GUIDE.md](docs/USER-GUIDE.md) | **Bắt đầu ở đây** — dùng sản phẩm, đầu tới cuối |
| [docs/SELLING-POINTS.md](docs/SELLING-POINTS.md) | Vì sao suite này làm khác |
| [docs/KNOWN-GAPS.md](docs/KNOWN-GAPS.md) | Những gì đã gỡ và những gì chưa làm |
| [docs/CONTEXT.md](docs/CONTEXT.md) | Từ vựng dùng chung |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | Hợp đồng giữa hub và agent |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Đang ở phase nào, còn gì phía trước |
| [docs/adr/](docs/adr/) | Các quyết định kiến trúc và lý do |

---

## Chạy tại máy

Chỉ riêng hub, không kèm agent:

```bash
cp .env.example .env
```

Sinh **hai** bí mật — chúng phải là **hai giá trị khác nhau**
([ADR 0005](docs/adr/0005-secret-and-key-management.md)). API **từ chối khởi động** nếu thiếu một
trong hai; không có giá trị dự phòng tự sinh, vì một khoá mã hoá tự sinh lúc boot sẽ lặng lẽ tạo
ra dữ liệu không giải mã được sau lần restart kế tiếp.

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
hub tự dựng knowledge base, nên image API cài thêm `git`, Node 20 và `@anthropic-ai/claude-code`
lên trên nền Python. (Không có chromium — hub không chạy trình duyệt nào.)

```bash
docker compose exec api sh -c 'git --version && node --version && claude --version'
```

### Hai thứ phải tự cung cấp

Stack không thể tự có, và thiếu chúng thì lượt dựng knowledge base sẽ dừng ở trạng thái `error`
kèm thông báo thiếu cái gì — nó **không** làm hỏng request:

- **Một credential Claude** — upload trong *Claude Settings*, hoặc nhờ admin cấu hình tài khoản
  dùng chung.
- **Một kết nối repository kèm PAT** — trong *Integrations*, gắn vào project có repo cần clone.

> Volume `emehub-workspace` chứa bản clone của repository và — trong lúc dựng — một credential
> Claude đã giải mã. Hãy coi nó là dữ liệu nhạy cảm: không mount cho mọi người đọc, không sao chép
> tuỳ tiện.

### Chạy cả suite

`suite.sh` / `suite.ps1` là lớp mỏng bọc `docker compose -f docker-compose.suite.yml`, truyền vào
file `.env` của cả ba repo. Đọc phần đầu của hai script đó trước khi dùng.

Không bao giờ chạy đồng thời hai cách — cùng cổng, khác volume.

---

## Đóng góp

Quy ước, ranh giới kiến trúc và quy trình giao việc nằm ở [CLAUDE.md](CLAUDE.md). Nhánh mặc định
là `master`.

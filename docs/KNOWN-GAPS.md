# Những gì đã gỡ và những gì chưa làm

## Mở đầu

Tài liệu này ghi lại một đợt dọn dẹp có chủ đích trên EmeHub và ứng dụng anh em Q-Agent, theo
đúng một nguyên tắc: **một control không làm gì tốn kém hơn một tính năng còn thiếu.** Một nút
bấm giả khiến người dùng tin rằng hệ thống đã làm việc gì đó, và niềm tin sai đó đắt hơn nhiều
so với việc thừa nhận thẳng rằng tính năng chưa có.

Sau đợt này, **mọi control còn nhìn thấy trong giao diện đều làm một việc thật** — gọi một
endpoint thật, ghi vào một cột thật, và được đọc lại bởi một đoạn code thật. Những gì không đạt
được cả ba điều đó đã bị xoá hẳn (component, state, tầng dữ liệu, fixture, store key) hoặc ẩn
sau feature flag có ghi rõ điều kiện bật.

Bằng chứng kiểm chứng được: `grep -rn "Preview data" app/src` hiện không còn kết quả nào.

Tài liệu viết cho người đọc có nền kỹ thuật nhưng mới tiếp cận repo. Các số hiệu `#NNN` trong
cột PR thuộc repo `chuongnd2612/emehub`, trừ mục Q-Agent được ghi rõ.

---

## Đã gỡ khỏi EmeHub

| Tính năng | Vì sao nó không thật | Cần gì để làm thật | PR |
|---|---|---|---|
| Chuông thông báo trên header | Bấm vào chỉ toast một chuỗi hardcode `"3 notifications"`. Không có hệ thống thông báo nào trong hub | Một bảng notification, endpoint đọc/đánh dấu đã đọc, và nguồn sự kiện sinh ra thông báo | #199 |
| Project Settings › ba policy toggle (re-index khi merge, publish evidence, chặn khi index cũ) | `useState` cục bộ, reset mỗi lần điều hướng. `ProjectConfigIn` không có field nào cho cả ba. Chính notice bên dưới đã thừa nhận là không lưu | Ba cột trong `project_config`, mở rộng schema, và agent phải thực sự đọc chúng khi chạy | #199 |
| Settings › Workspace defaults | Sáu key ghi vào `localStorage`, không có nơi nào đọc lại | Một resource cấu hình cấp workspace, và ít nhất một consumer đọc nó | #199 |
| Settings › Notifications | Tương tự — ghi rồi không ai đọc | Như trên, cộng hệ thống thông báo ở hàng trên | #199 |
| Settings › save bar và toàn bộ draft machinery, `store/preferences` | Hai card trên biến mất thì draft không còn field nào. Một nút Save không có gì để lưu là cùng một lời nói dối ở hình dạng khác | Không cần — component `SaveBar` được giữ lại và đã được dùng thật ở #203 | #199 |
| Users › tab Invitations | Seed từ ba người bịa. `Revoke` chỉ splice một mảng cục bộ mà không đụng tới tài khoản hub đã tạo; `Resend` chỉ toast. `POST /auth/users/invite` tạo tài khoản ngay, nên không bao giờ có gì ở trạng thái pending | Đổi invite thành hai bước: tạo bản ghi invitation pending, tài khoản chỉ sinh ra khi người được mời redeem token | #199 |
| Users › tab Roles | Bốn role bịa với số thành viên và checklist quyền tự nghĩ ra. Hub chỉ lưu `admin` và `member` | Một resource role/permission thật, cộng chỗ enforce quyền đó ở tầng API | #199 |
| Bảng Members › cột CLAUDE CREDENTIAL | Mọi dòng đều đọc "Not assigned". Không có ánh xạ nào giữa user và credential | Một quan hệ user ↔ credential, và endpoint trả về nó | #199 |
| Modal "Add knowledge" và cả bốn lối vào (quick action ở Overview, tab Knowledge, `ModalHost`, command palette) | `add()` đóng modal rồi toast "queued for indexing" mà không POST gì cả | Hub đã build knowledge thật qua `POST /projects/{key}/repos/{repo}/knowledge/build` — cần thiết kế lại lối vào quanh endpoint đó thay vì một modal riêng | #199 |
| Tab Knowledge › bảng nguồn, ô tìm kiếm, filter chip, click dòng | Đã không thể chạm tới từ trước: `getKnowledgeSources()` luôn trả về `[]` | Một registry knowledge-source thật. Notice thông tin hiển thị thay thế vẫn được giữ | #199 |
| Claude Settings › toàn bộ tab Agent preferences | Ba `useState` toggle, cộng hai card override không render dữ liệu và không có hành động — một card ghi thẳng "Placeholder · configuration unlocks at launch" | Một resource cấu hình hành vi agent, và agent phải đọc nó | #196 |
| Claude Settings › card "API key fallback" | Một tiêu đề đặt trên một notice giải thích rằng không có API key fallback. Không route nào lưu API key | Một đường lưu API key, nếu quyết định hỗ trợ nó | #196 |
| Claude Settings › nút Save changes toàn cục | Ship ra ở trạng thái `disabled` vĩnh viễn | Không cần — hai tab còn lại lưu theo từng thay đổi | #196 |
| Claude Settings › chip DEFAULT và mục "Set as default" | Hardcode và disabled vĩnh viễn. Chỉ có một tài khoản shared, không có gì để "mặc định" so với cái gì | Nhiều credential shared cùng lúc, cộng cột đánh dấu default | #196 |
| `setDefaultCredential()` + `SET_DEFAULT_UNAVAILABLE` | Stub đằng sau mục menu trên, thiết kế ra để luôn từ chối. Không có call site nào | Như trên | #196 |
| Claude Settings › slider "Parallel agent runs" | Không ai đọc. Không endpoint, không agent, không config | Một cột concurrency và một scheduler thực sự tôn trọng nó | #196 |
| Trường `fastModel` trong model preferences | Field duy nhất của resource mới mà không có reader. `resolve_for_run()` chỉ trả `(mainModel, effort)`. Hub chỉ có đúng một đường gọi Claude, không có pass phụ nào đáng chạy trên model rẻ hơn | Một lời gọi Claude thứ hai (tóm tắt, phân loại) để gắn nó vào. Migration `0014_drop_fast_model` gỡ cột | #198 |
| `getSharedCredentials()` và interface `SharedCredential` | Adapter dịch credential shared đơn lẻ thành một danh sách. Docstring của nó khai là phục vụ popover credential, nhưng popover đã đọc `getCredentialState()` trực tiếp từ lâu. Xác nhận không còn call site nào trước khi xoá | Không cần | #202 |

### Dọn kho

Không phải tính năng, nhưng cùng tinh thần — repo không nên giữ những thứ không ai dùng, nhất
là khi repo đó giữ toàn bộ credential của suite:

- Hai snapshot secret cũ, `.env.bak.pre-oneorigin` và `.env.bak.pre-sso-20260805-175924`, còn
  nằm ở gốc repo sau hai lần migration. Cả hai khớp rule `.env.*` trong `.gitignore` nên chưa
  bao giờ được track — xoá không tạo diff, nhưng chúng là credential thật nằm trên đĩa. (#192)
- `design/design_handoff_emehub/assets/` giữ bản sao byte-identical của hai logo đã có trong
  `app/public/assets/`. Cả hai thư mục đều được track, tức là khoảng 2.3 MB binary trùng lặp
  đi vào lịch sử git. Sáu tham chiếu được sửa trước khi xoá, trong đó ba là `<img src>` sống
  trong prototype HTML. (#192)
- Hai logo được nén lại: `eme-3d-logo.png` từ 1 832 306 B xuống 367 217 B, `eme-3d-logo-cut.png`
  từ 531 777 B xuống 115 561 B, giữ nguyên 1774×887. Sai số trung bình trên pixel nhìn thấy là
  1.9/255 và 1.4/255. (#192)
- Sau đó `app/public/assets/eme-3d-logo.png` bị xoá hẳn: **không có gì load nó.** Vì nằm trong
  `public/`, Vite vẫn copy nguyên vào `dist/` bất kể có import hay không. (#194)
- `design/DESIGN_SYSTEM.md:214` trỏ tới `assets/eme-3d-logo-cut.png`, một đường dẫn đã gãy từ
  commit `d5e7ae8` — không phải hệ quả của đợt nén logo. (#194)

---

## Đã gỡ hoặc tạm ẩn ở Q-Agent

Repo `chuongnd2612/q-agent`, các PR dưới đây thuộc repo đó.

### Đã xoá hẳn

| Tính năng | Vì sao nó không thật | Cần gì để làm thật | PR |
|---|---|---|---|
| Card "Services healthy: N / N" | Hai con số là **cùng một biểu thức** `len(services)`, và không có health check nào đằng sau. "Services" thực chất là nhãn logger suy ra bằng regex. Payload, wire type và docstring của endpoint đều được dọn theo; lưới stat từ 4-up còn 3-up | Một health probe thật cho từng service | #674 |
| Chuỗi terminal `q-agent · kubectl logs -f --all-services` | Không có Kubernetes ở bất kỳ đâu — triển khai bằng docker-compose và panel hiển thị một ring buffer 200 dòng trong tiến trình. Đã đổi thành `q-agent · api · in-memory log buffer` | Không cần — chuỗi mới mô tả đúng cái đang chạy | #674 |
| Tuỳ chọn framework "Selenium" ở CreateRunModal | Chọn được và có persist vào `Run.framework`, nhưng mọi spec đều bị đóng dấu cứng `"Playwright"` và chỉ Playwright chạy — chọn Selenium thì vẫn nhận Playwright. Còn một lựa chọn thì segmented control không còn là lựa chọn, nên FRAMEWORK giờ là một pill tĩnh; `runFramework` cũng rời khỏi store | Một runner Selenium thật | #676 |
| Danh sách ENVIRONMENT hardcode `Staging / Production / Local` | Backend resolve base URL theo **so khớp tên không phân biệt hoa thường** với environment của chính project, vốn là free text người dùng tự đặt. Không khớp thì rơi về project base URL **không cảnh báo** — một project đặt tên "UAT" và "Dev" sẽ lặng lẽ gửi mọi run tới sai host | Đã làm thật: `GET /projects/environments` trả về đúng tập tên mà matcher có thể khớp, đọc từ chính những row đó. Không có tên nào thì hiển thị một dòng nói run sẽ dùng base URL của project | #676 |
| Luồng "Forgot password" và lời hứa gửi email | Không có mailer nào trong codebase — `POST /auth/request-reset` tự ghi `# DEV STUB` trong comment của mình, và grep `smtp/sendmail/mailer/email_service` không ra kết quả. Người dùng bấm "Forgot password?" và nhận một màn hình xanh nói *"Check your inbox — we sent a reset link"*, rồi không có email nào tới | SMTP thật. Trong lúc chờ, modal invite giờ hiện thẳng link `/forgot?token=…` trong một ô read-only kèm nút Copy, và nói rõ là không có email nào được gửi | #675 |

Nửa "token" của luồng đó **không bị đụng tới** — `/forgot?token=…` cũng là đường redeem của
invite nên phải tiếp tục hoạt động. Endpoint `POST /auth/request-reset` cũng được giữ nguyên,
chỉ là không còn lối vào từ giao diện.

### Đã làm thật thay vì xoá

| Tính năng | Vấn đề | Đã làm gì | PR |
|---|---|---|---|
| Reports › Export | Nút export không xuất gì | Tải về CSV thật của các report đang có (`id, runId, executionId, overallResult, passRate, passed, failed, durationS, env, createdAt`), theo đúng pattern Blob mà Audit Log đã dùng. Disable khi chưa có report, đổi nhãn thành "Export CSV" | #674 |
| Audit Log › toolbar Export/Clear | Toolbar nằm trên tab switcher, nên khi đang xem Backend Logs thì "Export CSV" lặng lẽ export dữ liệu **activity** và "Clear log" lặng lẽ xoá dữ liệu activity | Toolbar chỉ render khi tab activity đang active. Clear không thể bám theo dataset đang hiển thị vì không có thao tác backend nào xoá được ring buffer | #674 |
| Settings › slider số worker | Copy của chính nó gọi đây là giá trị mặc định — *"Default up to {{n}} cases at once per Run"* — nhưng không có gì đọc, trong khi một slider trông y hệt trong Create Run modal mới là cái thực sự tới `Run.workers` | Modal giờ seed `runWorkers` từ `settings.parallel` khi mở. Seed **một lần mỗi lần mở**, chặn bằng ref chứ không phải dependency `open`, vì query settings có thể resolve sau khi modal đã hiện. Copy cũ không cần sửa — nó trở thành đúng | #677 |

### Ẩn sau feature flag

Hai toggle dưới đây persist đúng và đọc lại được sau reload, nhưng **không có gì đọc chúng khi
chạy**. Chúng được ẩn chứ không xoá: settings key, schema field và cột `Run.retry_policy` đều
giữ nguyên, nên khi reader xuất hiện thì chỉ cần bật cờ. Cờ nằm ở `app/src/config/features.ts`,
mọi cờ đang `false`, mỗi cờ có comment ghi chính xác điều kiện để bật.

| Toggle | Đang chờ gì | PR |
|---|---|---|
| Settings › "Auto-retry flaky tests" (`retryFlaky`) | `_PLAYWRIGHT_CONFIG_TEMPLATE` trong `api/app/services/playwright_runner.py` không có key `retries:` nào cả, nên mọi run dùng mặc định 0 của Playwright. `Run.retry_policy` được ghi lúc tạo và cũng không ai đọc. Bật khi template sinh ra `retries:` từ `settings.retryFlaky` và một run thực sự retry | #677 |
| Settings › "Screenshot on failure" (`screenshotOnFail`) | Cùng template đó hardcode `screenshot: 'on'`, nên screenshot được chụp ở mọi case bất kể toggle. Bật khi template lấy giá trị đó từ `settings.screenshotOnFail` | #677 |

---

## Chip credential còn thiếu gì

Chip credential trên header của hub hiện hiển thị model thật từ `GET /me/model-preferences`,
context window dưới dạng pill `1M ctx`, mức effort, tên file / subscription / scope / hạn dùng
/ lần refresh gần nhất của credential, nút **Test credential**, một nút refresh, skeleton lúc
tải, tooltip trạng thái, và usage: **hai cửa sổ cuốn chiếu** — `CURRENT SESSION` và
`CURRENT WEEK`, mỗi cửa sổ một dòng `N tokens · N requests · resets …` với chi phí làm số
chính — phân rã bốn chiều của tuần (input, output, cache read, cache write), rollup
`BY MODEL`, `costMonth`, `requestsToday`, `avgLatencyMs`.

Chip anh em ở QAgent (`ClaudeStatsButton`) vẫn hiển thị nhiều hơn thế. Bốn mục dưới đây **cố ý
không được port sang**, và không có thứ thay thế nào được bịa ra cho chúng.

### Cần thêm backend

| Thiếu | Vì sao chưa có |
|---|---|
| Email tài khoản / tổ chức | `ClaudeCredentialMeta` không có field nào trong hai field đó |

### Bất khả thi ở kiến trúc hiện tại

| Thiếu | Vì sao không dựng được |
|---|---|
| Health dot ba trạng thái / "Claude CLI unavailable" | Cần `stats.operational`, tức là câu trả lời cho "CLI cục bộ có chạy được không". Hub không có probe nào và không có field tương đương, nên dot giữ nguyên bốn trạng thái suy ra từ credential và không thêm chiều sức khoẻ nào |
| Thanh weekly **budget** | QAgent vẽ thanh này theo một setting `weekBudget` do người dùng tự đặt. Hub không có setting đó, nên không có ngưỡng nào để vẽ. Đây **không** phải hạn mức của gói — hạn mức gói nay đã có, xem bên dưới; budget tự đặt và hạn mức gói là hai thứ khác nhau, và chỉ thứ thứ hai là lấy được |

### Đã lấp (#212) — và một mục ở trên từng ghi sai

Trước #212, bảng "Bất khả thi" còn có hai dòng nữa: gauge "% of plan used" và thanh weekly
budget, với lý do là *hub không bao giờ chạy Claude CLI nên không biết hạn mức nào cả*.

**Lý do đó sai, và sai ở ngay tiền đề.** Ghi lại đầy đủ, vì một mục "bất khả thi" ghi sai
còn tệ hơn một mục còn thiếu:

1. Image của API **có** sẵn Claude CLI — `claude 2.1.197` tại `/usr/local/bin/claude` trong
   `emesoft-emehub-api-1`, cài để chạy knowledge build (`api/app/services/claude_cli.py`).
   Câu "hub không bao giờ chạy CLI" đơn giản là không đúng.
2. Quan trọng hơn: **con số đó không đến từ CLI.** Màn `/usage` của CLI chỉ là bản vẽ lại của
   một lời gọi HTTP có xác thực. Hub gọi thẳng lời gọi đó được, vì hub đang giữ chính
   credential cần dùng và đã giải mã nó theo từng user
   (`claude_credentials.resolve_material`). Không cần subprocess, không cần ghi plaintext ra
   đĩa, không cần parse output của TUI.

| Từng ghi là bất khả thi | Dựng bằng gì |
|---|---|
| Gauge "% of plan used" | `api/app/services/claude_plan_limits.py` gọi `GET https://api.anthropic.com/api/oauth/usage` với access token OAuth của credential mà user resolve tới (header beta `oauth-2025-04-20`) — cùng endpoint mà `/usage` của CLI tiêu thụ. `five_hour` → dòng session, `seven_day` → dòng tuần. Cache 180s **khoá theo id dòng credential, không phải id user**, refresh ở thread nền nên request không bao giờ chờ mạng |
| Thời điểm reset thật | Cùng payload trả về `resets_at` do Claude công bố. Nó thắng con số hub tự suy ra (lời gọi đầu tiên trong cửa sổ + 5h). Chỉ hiện một trong hai, không bao giờ hiện cả hai |

Token đi đúng một đường: Postgres (đã mã hoá) → `crypto.decrypt` trong `resolve_material` →
một biến cục bộ → header `Authorization` của đúng một request → hết frame là mất. Nó không
ra file, không ra log, không ra message của exception, không ra response body. Response chỉ
mang `pctUsed`, `resetsAt` và `limitsStatus`.

Mọi thất bại đều cho cùng một câu trả lời: `pctUsed = -1` (không biết) và
`limitsStatus = "unavailable"` — không credential, token hết hạn, upstream từ chối, payload
không parse được. Không bịa số, không ném 500. Khi không biết, headline của dòng rơi về chi
phí như trước, đúng đường dự phòng mà chính QAgent dùng.

**Không có đường dự phòng scrape CLI.** QAgent giữ một đường như vậy vì nó đọc credential từ
đĩa và có thể đọc hụt; hub thì không, nên không có trường hợp nào scrape thành công mà lời
gọi trên thất bại — scrape cũng chỉ đọc một bản sao của cùng token đó. Đổi lại sẽ phải ghi
plaintext vào workspace volume (thứ ADR 0007 chỉ cho phép trong knowledge build), spawn một
TUI ngay trên thao tác mở popover, và nuôi một parser nhắm vào output đổi hình theo từng bản
CLI. Một chữ "không biết" trung thực đáng giá hơn.

### Đã lấp (#210)

Ba mục từng nằm ở hai bảng trên đã dựng được, và **không cần migration nào** — mọi cột đều đã
có sẵn trên bảng `claude_usage`, đây thuần tuý là aggregation:

| Từng thiếu | Dựng bằng gì |
|---|---|
| Rollup `by_model` | `stats()` group theo cột `model` có sẵn trên từng dòng, trong cửa sổ tuần, sắp theo chi phí giảm dần. Dòng nào agent không gửi tên model thì `model` là `""` — SQL gom chúng thành đúng một nhóm, và UI gọi nhóm đó là `Unattributed` |
| Số request và chi phí theo tuần | Cùng một `SUM`/`COUNT` như token tuần, chỉ là trước đây service không trả ra. Khoá `week` mới đứng cạnh `weekTokens`, không thay thế nó |
| Cửa sổ "Current session" | Từng bị xếp nhầm vào bảng "bất khả thi". Hub **không** cần CLI để có cửa sổ này: mỗi dòng `claude_usage` đã có `ts`, mà đó là toàn bộ đầu vào một cửa sổ cuốn chiếu cần. Định nghĩa lấy đúng của QAgent (`claude_usage_reader._SESSION_WINDOW`) — **5 giờ cuốn chiếu, reset sau lần gọi đầu tiên trong cửa sổ đúng 5 giờ**, tức cửa sổ usage của chính Claude. Đó cũng là lý do giờ reset hiếm khi tròn. UI ghi kèm `rolling 5h` để con số tự giải thích |

Chi phí là `SUM(cost_usd)`, không phải tính lại: agent gửi kèm `cost_usd` trên từng call qua
`POST /credentials/claude/usage` và hub lưu nguyên. QAgent phải mang một bảng giá theo model
vì nó dựng lại chi phí từ transcript vốn không ghi chi phí; hub không ở tình cảnh đó, nên
**không thêm bảng giá nào** — một bảng giá cũ sẽ lặng lẽ báo sai tiền.

Sáu khoá cũ của `stats()` giữ nguyên hình dạng, vì `screens/Claude/CredentialsTab.tsx` render
chúng.

Panel có một dòng disclaimer nói rằng chi phí là ước lượng từ token usage và các con số chỉ
giới hạn trong những gì agent đã báo về.

Nút **Test credential** (`POST /credentials/claude/test`) là một phép kiểm tra lưu trữ: xác
nhận credential đã lưu tồn tại, giải mã được, parse được và chưa hết hạn. **Nó không gọi
Claude.** Panel nói đúng như vậy, dùng lại nguyên văn câu chữ từ Claude Settings › Connection
health, và cùng hằng số đó là nội dung toast khi thành công — để một kết quả xanh không thể bị
đọc thành "Claude đã trả lời".

---

## Việc chưa xong ở tầng kiến trúc

Phần này không nhắc lại nội dung, chỉ chỉ đường. Ba nguồn dưới đây là chỗ đọc chi tiết.

**Cutover cho agent** — `docs/ROADMAP.md`, Phase 3 đến Phase 5. Cả ba phase đều ở trạng thái
"Hub side: done. Agent cutover: not started". Nửa của hub đã xong và gọi được; nửa còn lại nằm
ở hai repo agent. Phase 3 còn ghi rõ cạnh sắc nhất: mọi giá trị mã hoá của QAgent dùng khoá dẫn
xuất từ `QAGENT_SECRET_KEY`, còn hub dùng `EMEHUB_ENCRYPTION_KEY` riêng, nên di trú là
decrypt-bằng-khoá-cũ rồi re-encrypt-bằng-khoá-mới. Phase 5 mở đầu bằng một câu hỏi chưa có lời
đáp và câu hỏi đó chặn cả phase: D-Agent ở lại là công cụ chạy cục bộ hay trở thành dịch vụ
hosted.

**Sáu việc phía D-Agent** — `docs/DAGENT-HANDOFF.md`, mục 1 đến 6: nhận lấy container image;
gỡ mount `/dagent` khỏi hai patch proxy; bỏ auth fail-open; nhận token của hub như một session;
thêm health endpoint; và chạy được bên trong container.

**Phần "Not yet built" của README Q-Agent** — không có job queue hay worker pool (mọi việc dài
chạy trong daemon thread trong tiến trình, không sống qua restart); không có Playwright phía
server trong image Docker; không có phiên browser tương tác phía server; không có CI/CD trigger
và không có runner Cypress/Selenium; không có unit test frontend; installer desktop của Local
Agent chỉ có bản Windows.

**Hai điều trong README đó đã cũ, đã kiểm chứng lại:**

- Mục "No SSO/OIDC" **không còn đúng.** SSO qua hub đã có: `POST /auth/sso/complete` tồn tại
  trong `api/app/routers/auth.py`, có cờ `QAGENT_HUB_SSO_ENABLED` gác, và một chuỗi commit đã
  merge quanh nó (`a617abc`, `8ba11a1`, `8f79f1e`, `30653b6`).
- Mục "The backend suite is currently red — 22 of 520 tests fail on `master`" cũng đã cũ.
  Issue `q-agent#469` mà nó dẫn tới đang ở trạng thái **CLOSED**, và hai commit sửa suite đã
  merge (`4a012e7`, `38fa1dd`). Con số 520 cũng không còn phản ánh quy mô hiện tại — đếm khai
  báo `def test_` trong `api/tests/` cho ra 1209. Bản thân tình trạng xanh/đỏ hiện tại **chưa
  được xác minh trong đợt này**, vì không có test nào được chạy.

---

## Lỗi đã sửa trong đợt này

Không phải mọi thứ đều là gỡ bỏ. Đây là những lỗi thật, tìm ra trong lúc dọn:

- **Trang landing bỏ qua công tắc product availability và mặc định về "Live".** Tắt một sản
  phẩm trong Settings đã chặn được app và edge proxy, nhưng không chặn trang landing — màn hình
  đầu tiên mà bất kỳ ai cũng thấy. `getProducts()` suy ra `enabled` từ `GET /agents`, vốn chỉ
  dành cho audience của hub, nên một khách chưa đăng nhập luôn fail lần đọc đó và fallback
  `enabled: target?.enabled ?? true` đánh dấu mọi sản phẩm là mở. Giờ nó đọc `GET /agents/{id}/open`
  vốn đã public, và **đọc lỗi nghĩa là đóng**. Riêng launch state vẫn degrade theo chiều ngược
  lại, vì một nút Launch chết còn hơn một màn Overview trắng — hai câu hỏi khác nhau. Ngoài ra
  card landing trước đây không hề tham chiếu `enabled`, nó rẽ nhánh theo `product.live`, vốn chỉ
  là badge của thiết kế. (#199)
- **"Add knowledge" toast báo thành công mà không POST gì.** (#199)
- **Invitations và Roles dựng trên ba người bịa và bốn role tự nghĩ.** Chính giao diện đã tự
  khai điều đó — đây là bằng chứng trung thực nhất còn lại. Notice của tab Roles viết: *"Preview
  data. The hub stores two roles — Admin and Member — and has no permissions resource, so these
  cards and their checklists are the design, not live configuration."* Notice của tab
  Invitations viết: *"Preview data. An invitation creates the account straight away, so the hub
  has nothing pending to list. This shows what this browser has sent plus the seeded examples,
  and clears on reload — revoking here does not delete the account."* (#199)
- **Card usage ghi "Usage this month" trên một con số tính theo tuần.** Chỉ dòng `$…` là theo
  tháng. Số liệu tổng hợp luôn thật — `claude_usage.py` chạy SUM thật — chỉ nhãn là sai. Tiêu đề
  giờ không mang phạm vi ("Claude usage") và mỗi con số tự mang cửa sổ thời gian của nó. Không
  con số nào thay đổi. (#196)
- **Hai ô tên trong modal Add a user ngắn và bẹp theo chiều dọc.** Nguyên nhân nằm ở
  `components/ui/Input.tsx` chứ không ở modal: `className` được áp vào field box bên trong, còn
  một input có label thì bọc box đó trong `<label className="flex flex-col gap-[7px]">` — và
  chính wrapper đó mới là flex item của hàng, nhưng không mang class width nào nên đứng nguyên
  ở fit-content. `flex-1` mà modal yêu cầu không bao giờ tới được flex item, và khi áp lên field
  box (cha là `flex flex-col`) thì nó tác động lên **chiều cao**, đè lên `h-9` và làm box sụp
  còn 20.75px. Hàng chuyển sang `grid grid-cols-2`, và wrapper được thêm `min-w-0`. (#195)
- **"Services healthy: N / N" là một phép lặp lại chính nó** — hai vế cùng là `len(services)`.
  (q-agent #674)
- **Toolbar của Audit Log thao tác trên sai dataset** — nằm trên tab switcher nên khi xem
  Backend Logs thì Export và Clear vẫn tác động lên dữ liệu activity. (q-agent #674)
- **Chuỗi `kubectl` giả trong panel log** trong khi triển khai bằng docker-compose. (q-agent #674)
- **Lưu cấu hình project làm trắng cả màn hình.** `load` của `ProjectDetail` đặt
  `status = "loading"` và màn hình return sớm với `LoadingState` toàn màn ở trạng thái đó, nên
  lần refetch sau khi lưu unmount toàn bộ cây tab: mất header, form bị huỷ rồi dựng lại, mất vị
  trí cuộn và mất state cục bộ của tab. Người dùng đọc nó thành "trang vừa reload", trong khi
  không có `location.reload()` nào trong repo. `load` giờ nhận `{ silent }`. (#203)
- **Save bar vô hình.** Tìm ra lúc chạy thật, không phải lúc review: `position: fixed` resolve
  theo ancestor gần nhất có `transform`, `filter` hoặc `backdrop-filter` — và mọi màn hình cần
  bar này đều nằm trong một ancestor như vậy, vì shell mở từng màn bằng `animate-fade-in-up`
  mà fill-mode `both` để lại `transform: matrix(1,0,0,1,0,0)` vĩnh viễn. Đo được: bar bị ghim
  vào đáy một container cao 1507px trong viewport 934px, tức 573px dưới nếp gấp. Sửa bằng đúng
  cách CLAUDE.md đã quy định cho dropdown và popover — `createPortal` tới `document.body`. (#203)
- **Một tài khoản mới bị hiển thị một credential shared đã hết hạn mà nó không hề có.** Ba
  trạng thái cùng một lỗi: `source` fallback về `"shared"` cho mọi mode không phải `"own"`, kể
  cả `"none"`. Pill trạng thái, dòng phụ trên header và công tắc Shared|Personal giờ đều nói
  rằng không có credential nào được gắn. Đây là trạng thái đầu tiên mà một tài khoản mới gặp
  phải. (#202)
- **Hint trong modal invite render nguyên chuỗi `{{email}}`.** `users.invite.linkHint` nhận một
  interpolation nhưng `t()` được gọi mà không truyền, khác với `linkSubtitle` ngay bên cạnh.
  `check-i18n.mjs` không bắt được lỗi này vì key vẫn resolve được. (q-agent #679)

---

## Nợ kỹ thuật còn lại

Phần trung thực còn lại. Không có mục nào dưới đây được che giấu hay giảm nhẹ.

- **Toàn bộ test suite đang được làm lại và đã cố ý không chạy trong đợt này**, nên nhiều khả
  năng có test đỏ. Cụ thể: `_resolve_model()` đổi signature ở #196 (giờ nhận `db` và `owner_id`,
  trả `(model, effort)` từ `model_preferences.resolve_for_run`). Bất kỳ test nào bám vào chữ ký
  cũ sẽ hỏng.
- **Migration `0013_model_preferences` chỉ được kiểm chứng trên SQLite, chưa bao giờ trên
  Postgres**, vì Docker engine trên máy làm việc trả 500 cho mọi request. `0014_drop_fast_model`
  cũng ở tình trạng đó. `upgrade head` và `downgrade -1` đều round-trip sạch trên SQLite.
- **Phần kiểm chứng Playwright của #202 chạy với toàn bộ `/api/*` bị stub**, cùng lý do trên.
  Cơ chế pub/sub của chip là hoàn toàn client-side nên phép thử "đổi model không cần reload" là
  thật; còn các con số hiển thị là giá trị giả.
- **Cạnh tranh sửa đồng thời ở #203.** Form giữ nguyên mount qua các lần refetch, nên effect
  reset field được gác hai lớp: nó key theo **giá trị đã serialize** chứ không theo identity của
  object, và nó return sớm khi giá trị đến bằng đúng baseline đang giữ (`save` seat baseline từ
  chính response của PUT, nên lần refetch theo sau là component đang bắt kịp chính nó). Hệ quả
  còn lại: nếu giá trị trên server **thật sự đổi** trong lúc người dùng đang giữ một draft chưa
  lưu — người khác sửa cùng project — thì `incomingKey !== savedKey`, effect chạy, và
  `setDraft(incoming)` thay thế draft đó. Lưu ý PR body của #203 mô tả nhánh này ở khía cạnh
  tích cực ("a genuinely different saved config adopts itself into the form") và không nêu mặt
  mất dữ liệu; nhận định ở đây đọc từ code trong `ProjectConfigForm.tsx`.
- **README của Q-Agent đã cũ ở hai chỗ** — mục SSO và mục suite đỏ, xem phần trên. Chưa sửa.
- **Phần Status của `README.md` gốc repo này cũng đã cũ**: nó vẫn dẫn #50 và liệt kê "API keys,
  roles, invitations, Overview activity/KPIs" là những màn có UI mà không có backend, "và tự nói
  ra điều đó thay vì hiển thị fixture như thật". Sau #199 và #196 thì các màn đó đã bị gỡ, không
  còn tự nói gì nữa.
- **`design/DESIGN_SYSTEM.md` là một bản gần-trùng đã trôi** so với
  `design/design_handoff_emehub/Q-Agent-DESIGN_SYSTEM.md` — cùng cách đánh số dòng, khác md5.
  Bản nào là bản có thẩm quyền là một câu hỏi thật (CLAUDE.md chỉ định bundle handoff là binding),
  và hợp nhất chúng xứng đáng một quyết định riêng. #194 chỉ sửa đường dẫn gãy.
- **`POST /auth/request-reset` ở Q-Agent vẫn còn**, chỉ là không còn lối vào từ giao diện. Xoá
  hẳn sẽ đụng vào API test nằm ngoài phạm vi slice đó, và một endpoint không ai chạm tới được
  thì không nói dối với người dùng nào. Cắm SMTP thật mới là cách sửa đúng.
- **`ReviewCenter.tsx` vẫn đưa ra `Selenium` và `Cypress`** trong `automationOptions`. Đây là
  nhãn metadata của một test case chứ không phải lựa chọn executor như trường hợp đã xoá ở #676,
  nên nó không âm thầm đổi hành vi run — nhưng nó vẫn đặt tên hai công cụ mà nền tảng không chạy
  được, và đáng được xem lại.
- **Không có container nào được rebuild trong đợt này.** Mọi PR ở trên đều cố ý không chạy
  `docker compose up -d --build`; các image đang chạy là cũ cho tới khi có một lần rebuild gộp.

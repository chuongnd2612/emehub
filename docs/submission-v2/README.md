# docs/submission-v2 — bộ tài liệu bản trước

Bốn tài liệu ở đây là **bộ dự thi bản trước [PR #257](https://github.com/chuongnd2612/emehub/pull/257)**,
giữ lại nguyên vẹn. Byte-identical với `docs/submission/` tại commit `234d150` — không rebuild,
không sửa.

> **Một ngoại lệ:** `EmeHub - Thong tin du an` được build lại khi `docs/ACCOUNT.md` thêm tài khoản
> demo member. Thông tin đăng nhập mà **không** khớp giữa hai bộ tài liệu đưa cho Ban Giám khảo là
> đúng cái drift mà `build-docs.ps1` tồn tại để chấm dứt, nên tài liệu này ưu tiên khớp nguồn hơn
> là đóng băng bytes. Ba tài liệu còn lại vẫn nguyên bản `234d150`.

| Tài liệu | Nguồn Markdown |
|---|---|
| `EmeHub - Tong quan san pham` | [`README.vi.md`](../../README.vi.md) |
| `EmeHub - Huong dan su dung` | [`docs/USER-GUIDE.md`](../USER-GUIDE.md) |
| `EmeHub - Diem noi bat` | [`docs/SELLING-POINTS.md`](../SELLING-POINTS.md) |
| `EmeHub - Thong tin du an` | [`docs/ACCOUNT.md`](../ACCOUNT.md) |

## Quan hệ với bộ hiện hành

| | Bộ này | `docs/submission/` |
|---|---|---|
| Cấu trúc | 4 tài liệu theo cách trình bày cũ | 14 tài liệu theo cấu trúc BTC (`docs/product/`) |
| Manifest | `docs/tools/manifest-v2.json` | `docs/tools/manifest.json` |
| Trạng thái | **Đóng băng** — giữ để đối chiếu và dự phòng | Bộ đang dùng để nộp |

`docs/SELLING-POINTS.md` là nguồn dùng chung của **cả hai** bộ, nên sửa nó là sửa cả hai.

## Rebuild

Bộ này vẫn build lại được — Markdown vẫn là source of truth:

```powershell
pwsh docs/tools/build-docs.ps1 -ManifestFile manifest-v2.json -OutDir docs/submission-v2
```

> Rebuild sẽ ghi đè các file đang có, và output mới **không** byte-identical với bản đóng băng
> (docx là zip, mang timestamp). Nội dung thì giống. Chỉ rebuild khi thật sự cần.

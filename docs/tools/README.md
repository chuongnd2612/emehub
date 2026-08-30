# docs/tools — building the submission documents

Markdown is the single source of truth. Every `.docx` and `.pdf` under
[`docs/submission/`](../submission/) is a **build artefact** of `build-docs.ps1`.

**Never edit an artefact by hand.** The next build overwrites it without warning, silently, and
the edit is gone. Edit the Markdown source and rebuild. This rule is the whole point of the
script: before it existed the same content lived in three or four formats that had already
drifted apart — two of them disagreed about the demo password.

## Build

```powershell
pwsh docs/tools/build-docs.ps1
```

Everything in `manifest.json`, into `docs/submission/`.

| Flag | Effect |
|---|---|
| `-Only <substring>` | Build just the matching entries — matches source path or output name |
| `-NoPdf` | `.docx` only. Skips Word entirely; use on a host without it |
| `-OutDir <path>` | Somewhere other than `docs/submission/` |
| `-KeepIntermediate` | Keep the preprocessed `.md` files. This is what officecli actually saw — start here when a document comes out wrong |

## What it needs

| Tool | Used for | Optional |
|---|---|---|
| **officecli** on `PATH` | Markdown → `.docx` | No |
| **Microsoft Word**, via COM | `.docx` → `.pdf` | Yes, with `-NoPdf` |

There is no pandoc, no libreoffice and no soffice on this host, which is why the route runs
through those two rather than the obvious one. Both were verified present before the script was
written.

## Adding a document

1. Write the Markdown.
2. Add an entry to [`manifest.json`](manifest.json):

```json
{
  "source": "docs/YOUR-DOC.md",
  "output": "EmeHub - Ten file khong dau",
  "title": "EmeHub — Tiêu đề có dấu"
}
```

`source` is relative to the repo root. `output` is the artefact's filename **without extension** —
keep it ASCII, since it becomes a filename someone will attach to an email. A missing `source`
fails the build loudly rather than skipping.

3. Rebuild.

Removing an entry is the mirror image, with one manual step: the script never deletes anything it
did not just write, so the artefacts of a dropped entry stay in `docs/submission/` until you remove
them yourself. Deleting whatever is no longer in the manifest would mean deleting files in
`-OutDir` on the strength of a config file — not a thing a build script should do unasked.

## Two things the script does that are not obvious

**It defines heading styles before adding the Markdown.** A blank officecli document has none, so
its Markdown expansion would reference `Heading1`/`Heading2` as-is and warn they are missing. Word
still *renders* those paragraphs — it falls back to direct formatting — but they are `Normal` as
far as the file is concerned, which costs the navigation pane, any table of contents, and the PDF
bookmark tree. Naming the styles `heading N` is what makes Word adopt them as its own built-ins
rather than treating them as custom styles that merely look like headings.

**It rewrites links before officecli sees them.** officecli's Markdown expansion degrades a link
to its visible text and drops the URL: `[t](u)` keeps `t`, and `![a](u)` becomes the literal `!a`.
In a printed document a URL that vanishes is worse than one that is ugly, so:

| In the Markdown | In the document |
|---|---|
| `[text](https://example.com)` | `text (https://example.com)` |
| `[text](../other.md)`, `[text](#anchor)` | `text` — the path means nothing in print, and the document it points at is in the same bundle |
| `![alt](img.png)` | `alt` — no picture is embedded, so the `!` would be noise |
| Anything inside `` ` `` or a fenced block | Untouched — a link in a code sample is sample text |

## Known limitations, inherited from officecli

- Table cells carry plain text; inline formatting inside a cell is lost.
- Nested blockquotes flatten to one level.
- No pictures are embedded.
- A "loose" list — a blank line between the marker and its fenced content — is not treated as item
  content.

None of these affect the documents currently in the manifest. If a new document needs one of them,
the fix is to write around it, not to hand-edit the artefact.

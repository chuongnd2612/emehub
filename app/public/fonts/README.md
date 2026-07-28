# Self-hosted fonts

No CDN — the app loads these from `/fonts/*` via `@font-face` in
`src/styles/fonts.css` (CLAUDE.md › Design › "Fonts self-hosted").

| File | Family / weight | Source |
|---|---|---|
| `satoshi-400.woff2` | Satoshi 400 | `api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900` |
| `satoshi-500.woff2` | Satoshi 500 | same |
| `satoshi-700.woff2` | Satoshi 700 | same |
| `satoshi-900.woff2` | Satoshi 900 | same |
| `jetbrains-mono-variable.woff2` | JetBrains Mono 400–600 | Google Fonts, latin subset |

JetBrains Mono ships from Google as a single **variable** woff2 covering
100–800, so one file serves 400/500/600 and the `@font-face` declares
`font-weight: 400 600` rather than three separate faces.

All files fetched successfully — nothing outstanding.

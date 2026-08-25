# Q-Agent — Design System

> AI-native design language for the Q-Agent QA-automation platform (EMESOFT).
> Extracted from the shipping components (`Q-Agent.dc.html`, `Q-Agent Mobile.dc.html`, `Q-Agent Auth.dc.html`, `PipelineRail.dc.html`, `Toast.dc.html`).
> Target feel: premium, dark, glassmorphic, futuristic — Cursor / Linear / Raycast / Vercel / Claude Desktop, never an enterprise CRUD panel.

---

## 1. Foundations

### 1.1 Color

**Base / surfaces**

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0a0a0f` | App background (deep charcoal). A fixed full-bleed layer sits under an animated Three.js particle/constellation field. |
| `--surface-panel` | `rgba(20,20,28,.55)` | Sidebar / primary frosted panels (over the ambient bg). |
| `--surface-card` | `rgba(255,255,255,.035)` | Glass cards, tiles, list containers. |
| `--surface-card-hover` | `rgba(255,255,255,.05)` | Hover fill on rows/cards/buttons. |
| `--surface-inset` | `rgba(255,255,255,.03)` | Nested/inset blocks inside a card. |
| `--surface-solid` | `#191921` / `#1b1b24` | Popovers, dropdowns, code/terminal chrome (opaque, no blur). |

**Borders & hairlines**

| Token | Value | Use |
|---|---|---|
| `--border` | `rgba(255,255,255,.07)` | Default card/panel border. |
| `--border-strong` | `rgba(255,255,255,.13)` | Popovers, focused containers. |
| `--border-subtle` | `rgba(255,255,255,.05–.06)` | Row dividers, internal separators. |
| `--divider` | `rgba(255,255,255,.09)` | Vertical rules in toolbars. |

**Text**

| Token | Value | Use |
|---|---|---|
| `--text` | `#ECECF1` | Primary text. |
| `--text-2` | `#dcdce4` | Secondary strong (table cells, values). |
| `--text-3` | `#c3c3d0` / `#c7c7d4` | Body copy in cards. |
| `--text-muted` | `#8b8b9e` | Meta, timestamps, captions. |
| `--text-faint` | `#7a7a8c` / `#6c6c7e` | Labels, placeholders, low-priority meta. |
| `--label` | `#6c6c7e` | Uppercase section labels (`letter-spacing:.08–.1em`). |

**Brand / accents** — purple → indigo is the signature; cyan is the secondary highlight. Keep accents to this family.

| Token | Value | Use |
|---|---|---|
| `--brand` | `#8b5cf6` | Primary purple. |
| `--brand-2` | `#6366f1` | Indigo (gradient partner). |
| `--brand-grad` | `linear-gradient(135deg,#8b5cf6,#6366f1)` | Primary buttons, logos, avatars, glyph chips. |
| `--brand-soft` | `#a78bfa` / `#c4b5fd` | Purple text on dark (IDs, links, accents). |
| `--cyan` | `#22d3ee` | Secondary highlight / gradients. |
| `--cyan-text` | `#67e8f9` | Monospace IDs, code accents. |
| `--cyan-grad` | `linear-gradient(135deg,#22d3ee,#6366f1)` | Project/secondary glyph chips. |

**Semantic status** — each status is a `{color, tint-bg}` pair; badges use `color` text on the `.10–.16` alpha tint.

| Status | Text/dot | Tint background |
|---|---|---|
| Success / Passed / Approved | `#6ee7b7` (or `#10b981` for solid dots/counts) | `rgba(16,185,129,.10–.16)` |
| Warning / Pending / Running | `#fbbf24` (spinner `#f59e0b`) | `rgba(251,191,36,.10–.14)` / `rgba(245,158,11,.1)` |
| Error / Failed / Rejected | `#fb7185` (or `#f87171`) | `rgba(244,63,94,.10–.16)` |
| Info / Active | `#c4b5fd` | `rgba(139,92,246,.12–.16)` |

**Provider / integration brand colors** (glyph chips only): Azure DevOps `#0078d4`, Claude / AI terracotta `#d97757` = `rgba(217,119,87,…)`.

**Selection:** `::selection { background: rgba(139,92,246,.4); color:#fff }`

### 1.2 Ambient light & atmosphere

The dark base is never flat. Two blurred radial glows drift behind content, plus a live Three.js constellation:

```css
/* top-left purple bloom */
background: radial-gradient(circle, rgba(139,92,246,.28), transparent 62%);
filter: blur(30px);            /* animation: glowPulse 9s ease-in-out infinite */
/* bottom-right indigo bloom — 11s, 1s delay */
background: radial-gradient(circle, rgba(99,102,241,.26), transparent 62%);
```
Cards catch this light through `backdrop-filter: blur(22–28px)` — glass, not opacity.

### 1.3 Typography

| | Family | Notes |
|---|---|---|
| UI / display | **Satoshi** (Fontshare `400,500,700,900`) → fallback `'Segoe UI', system-ui, sans-serif` | All headings and UI text. |
| Mono | **JetBrains Mono** (`400,500,600`) | IDs (RUN-204, SUR-1428), code, keyboard hints, metrics, timestamps. |

**Weight scale:** display headings `900`; card/section titles `700–800`; body `500–600`; the design leans heavy — near-black weights with tight tracking for hero numbers.

**Type ramp (observed):**

| Role | Size / weight / tracking |
|---|---|
| Page hero `h1` | `28–32px / 900 / -.03em` |
| Detail `h1` | `24–26px / 900 / -.02–.03em` |
| Card title `h2` | `20–23px / 800 / -.02em` |
| Metric / KPI number | `22–34px / 900 / -.03em` |
| Section title | `13–15px / 700` |
| Body | `13–14px / 500 / line-height 1.5–1.6` |
| Secondary / meta | `11.5–12.5px / 500–600`, color `--text-muted` |
| Uppercase label | `9–11px / 600–700 / letter-spacing .06–.1em`, color `--label` |
| Mono ID | `10–12.5px / 600–700`, color `--cyan-text` or `--brand-soft` |

`text-wrap: pretty` on headings/body paragraphs.

### 1.4 Spacing, radius, elevation

- **App shell:** `padding:14px; gap:14px` between sidebar and content; everything floats.
- **Card padding:** `16–24px` (tiles `16–18px`, feature cards `20–26px`).
- **Gaps:** `8–14px` in grids/stacks; use flex/grid + `gap`, never margin runs.
- **Radius scale:** chips/badges `pill (20px)`; small controls `7–10px`; buttons `11–14px`; cards `16–22px`; panels/sidebar `22px`; glyph tiles `7–13px`.
- **Shadows:** panels `0 24px 60px -20px rgba(0,0,0,.6)`; popovers `0 24px 60px -18px rgba(0,0,0,~.7)`; brand buttons `0 6px 18px -4px rgba(139,92,246,.7)`. Soft, large-radius, downward — depth not hardness.

### 1.5 Scrollbars

```css
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.09);border-radius:8px;border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,.18)}
```

---

## 2. Components

All are inline-styled (no CSS classes) so they paint immediately as they stream. Patterns below are the canonical recipes.

### 2.1 Glass card
```
background: rgba(255,255,255,.035);
backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
border: 1px solid rgba(255,255,255,.07);
border-radius: 18–22px; padding: 18–24px;
```

### 2.2 Primary button
```
background: linear-gradient(135deg,#8b5cf6,#6366f1);
color:#fff; font-weight:700; border:none; cursor:pointer;
padding:12–13px 20–22px; border-radius:13–14px;
box-shadow:0 6px 18px -4px rgba(139,92,246,.7);
```
**Secondary/ghost:** `background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08); color:#c3c3d0`, hover → `rgba(255,255,255,.05)`.
**Tinted action:** brand or semantic tint bg + matching border + colored text (e.g. approve = `rgba(16,185,129,.x)` border, `#6ee7b7` text).
**Dashed “add”:** `border:1px dashed rgba(255,255,255,.16); background:transparent`.

### 2.3 Status badge (pill)
```
font-size:10.5–11px; font-weight:700; padding:3px 9–10px; border-radius:20px;
background: <status tint>; color: <status color>;
```

### 2.4 Glyph / avatar chip
Rounded square (`7–13px` radius) or circle, `22–46px`, centered glyph/initials, filled with `--brand-grad`, `--cyan-grad`, or a provider color. Avatars reuse `linear-gradient(135deg,#8b5cf6,#6366f1)` with white initials.

### 2.5 Sidebar nav item
`display:flex; align-items:center; gap:9px; padding:8px 10px; border-radius:10px`. Active = brand tint + `1px solid rgba(139,92,246,.3)`; idle hover → `rgba(255,255,255,.04)`. Optional trailing mono badge (`rgba(255,255,255,.08)` fill).

### 2.6 Popover / dropdown
Opaque `#191921`, `border:1px solid rgba(255,255,255,.13)`, `border-radius:12px`, shadow `0 24px 60px -18px`. Items are ghost buttons with a `#6ee7b7` check on the active option.

### 2.7 Command bar / search
Full-width ghost pill with search icon, muted placeholder (“Search or ask Q-Agent anything…”), and a mono `⌘K` hint chip (`rgba(255,255,255,.06)` fill, `.08` border).

### 2.8 Progress
- **Bar:** `6px` track `rgba(255,255,255,.08)`, fill `linear-gradient(90deg,#8b5cf6,#22d3ee)`.
- **Ring:** SVG, track `rgba(255,255,255,.07)`, stroke width `13`, animated `stroke-dashoffset`; big centered `900` number.

### 2.9 Input
```
background: rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.09);
border-radius:10px; padding:9px 12px;
```
Focus/active border shifts to `rgba(139,92,246,.x)` (brand).

### 2.10 Pipeline rail (`PipelineRail.dc.html`)
Horizontal 8-stage stepper reused across run screens (`stage` prop). Done = green, current = brand-lit, upcoming = muted. Always mount with `hint-size="100%,76px"`.

### 2.11 Toast (`Toast.dc.html`)
Bottom-centered glass pill; success uses the green ring/check draw-on animation (`toastIn`, `toastRing`, `toastCircle`, `toastCheck`) plus a countdown bar (`toastBar`).

---

## 3. Motion

Animation is core to the “alive” feel — intentional, spring-ish, never noisy. Standard keyframes (defined once in `<helmet>`):

| Keyframe | Use |
|---|---|
| `fadeInUp` (16px, .3–.5s) | Screen / card entrance (default). |
| `scaleIn` (.96→1) | Modals, popovers. |
| `slideIn` (14px X) | Drawer content, list items. |
| `drawerIn` (translateX 100%) | Right-side peek drawer. |
| `pulseDot`, `glowPulse` | Live status dots, ambient blooms. |
| `spin` | Loading spinners (`border-top-color` accent). |
| `floaty` (−9px, loop) | Hero/decorative float. |
| `think` | AI “thinking” 3-dot. |
| `caretBlink`, `shimmer` | Streaming text caret, skeletons. |
| `barGrow` | Chart bars. |
| `toast*`, `proc*`, `tour*` | Toasts, processing states, product tour. |

**Transitions:** hover elevation/fill via `transition` on transform/background; logo uses a 3D tilt `transform: perspective(820px) rotateX/Y` with `cubic-bezier(.2,.7,.3,1)`.

**Defaults:** entrance `.3–.5s ease both`; hover `~.2s`; respect intent — one purposeful motion per element, not many.

---

## 4. Iconography & imagery

- **Icons:** inline SVG, `stroke="currentColor"` (or a semantic color), `stroke-width:2–2.4`, `stroke-linecap/linejoin:round`, `viewBox 0 0 24 24`, sized `13–19px`. Feather/Lucide-style line icons.
- **No hand-drawn illustration.** Atmosphere comes from the Three.js particle field + radial blooms, not decorative SVG art.
- **Brand mark:** `app/public/assets/eme-3d-logo-cut.png` (EMESOFT 3D logo), rendered with a mouse-reactive tilt in the sidebar.

---

## 5. Voice & content

- Confident, concise, product-led. Sentence case in UI; UPPERCASE only for small tracked labels.
- Refer to the assistant as **Q-Agent**; frame it as an active collaborator (“ask Q-Agent anything”, “Q-Agent generated…”).
- Domain vocabulary: **Run** (`RUN-204`), **Ticket** (`SUR-1428`), test **Case**, **Suite**, **Pipeline** (8 stages), **Evidence**, **Provider** (Azure DevOps / Jira). IDs are always mono.
- Empty states are opportunities — a glyph, a one-line explanation, and a primary CTA, never a bare “no data”.

---

## 6. Principles (do / don’t)

**Do**
- Dark, glassmorphic, layered — depth via blur + soft shadow + ambient light.
- Purple→indigo brand, cyan highlight, semantic green/amber/rose. Max 1–2 accent hues per view.
- Heavy display weights + mono for anything ID/number/code.
- Flex/grid + `gap` for all layout; generous whitespace; everything floats with rounded corners.
- Purposeful micro-motion on entrance, hover, and live/AI states.

**Don’t**
- No opaque flat panels, dense tables-everywhere, or generic blue-and-white admin chrome.
- No saturated gradient wallpaper (the ambient blooms are subtle and blurred).
- No emoji in UI; no hand-drawn/complex SVG illustration.
- No CSS-class stylesheets in components — inline styles so the UI paints while streaming.
- Don’t introduce accent hues outside the purple/indigo/cyan + semantic set.

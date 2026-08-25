# Handoff: EmeHub — EMESOFT AI Operating Center

## Overview

EmeHub is the workspace/control plane for EMESOFT's AI agents (**Q‑Agent**, a QA-automation agent that is live, and **D‑Agent**, a developer agent that is a placeholder). Anything an agent needs is configured once in EmeHub and inherited by every agent run: Claude credentials, provider connections (Azure DevOps / Jira / GitHub), imported work items, per-project knowledge bases, people & access, and appearance.

The design is one dark, glassmorphic, single-page application with:

- a **marketing landing view** (hero, product cards, capability grid, CTA), and
- an **app shell** (fixed sidebar + sticky page header + scrolling content) with 8 pages.

## About the Design Files

The files in this bundle are **design references authored in HTML** — a working prototype that shows the intended look, motion and behaviour. **They are not production code to copy.** The task is to **recreate these designs in the target codebase's existing environment** (React, Vue, Svelte, SwiftUI, native — whatever the app already uses), using its established component library, routing, state management and styling conventions. If no environment exists yet, pick the most appropriate framework for the product and implement there.

Two prototype-only details to be aware of and to replace with real implementations:

1. The prototype is a single-file component with all data hard-coded in the class body (`PROJECTS`, `TICKETS`, `MEMBERS`, `SHARED CREDS` in state, `KNOWLEDGE`, `CONNECTIONS`, …). In production these come from APIs.
2. All styling is inline `style="…"` (a constraint of the prototype tool). In production use the codebase's normal styling approach. **Do keep the CSS-variable theme layer** described under *Theming* — the light/dark implementation depends on it.

## Fidelity

**High-fidelity (hifi).** Colours, type, spacing, radii, shadows, motion and copy are final. Recreate pixel-faithfully with the codebase's existing primitives. Design canvas is **1512 × 950** (desktop-first). Sidebar is a fixed 268 px; content is fluid; several tables assume ≥1100 px of content width. No mobile layout is designed — see *Responsive*.

---

## Screens / Views

### 0. App shell (wraps every app page)

- **Root**: `position:relative; display:flex; height:100vh; width:100%; padding:14px; gap:14px`. Everything floats over the ambient background.
- **Background stack** (all `position:fixed; inset:0`):
  1. `z-index:0` — flat fill `var(--bg)`.
  2. `z-index:1` — WebGL constellation canvas container (see *3D constellation*), `pointer-events:none`.
  3. `z-index:1` — bloom A: 660×660 circle, `top:-16%; left:-8%`, `radial-gradient(circle, var(--pt), transparent 62%)`, `filter:blur(34px)`, `animation:glowPulse 9s ease-in-out infinite`, `opacity` = ambient setting.
  4. `z-index:1` — bloom B: 740×740 circle, `bottom:-22%; right:-6%`, `radial-gradient(circle, var(--bloom2), transparent 62%)`, `blur(34px)`, `animation:glowPulse 11s ease-in-out infinite 1s`.
- **Sidebar** (`aside`): width 268 px, `flex-shrink:0`, column, `overflow-y:auto`, `background:var(--panel)`, `backdrop-filter:blur(28px)`, `border:1px solid var(--bd)`, `border-radius:22px`, `padding:18px 14px`, `box-shadow:0 24px 60px -20px var(--shadow)`. Contents top→bottom:
  1. **Logo button** → returns to the landing view. `app/public/assets/eme-3d-logo-cut.png`, `width:100%`, wrapped in a tilt layer (see *Motion*), `filter:drop-shadow(0 12px 20px var(--shadow))`.
  2. **Product lockup**: 36 px rounded-square (`var(--pg)` gradient, star glyph, `box-shadow:0 6px 18px -4px var(--pglow)`) + `Eme` in `var(--txt)` and `Hub` filled with the `--silver` metal gradient (`background-clip:text`), 17 px/900/-.03em; sub-label `AI OPERATING CENTER` 9 px/700/.12em `var(--muted)`.
  3. **Nav** — one flat list; group headings `WORKSPACE` and `PLATFORM` are 10 px/700/.12em `var(--label)`, `padding:12px 6px 7px`. Items: `display:flex; gap:10px; width:100%; padding:9px 10px; border-radius:11px; font-size:13px; font-weight:600`, 18 px icon slot, label, optional mono badge (`10px/700`, `padding:2px 7px`, pill).
     - idle: `background:transparent; border:1px solid transparent; color:var(--muted)`; badge `background:var(--bd); color:var(--muted)`
     - hover: `background:var(--bd3)`
     - active: `background:var(--pt); border:1px solid var(--pb); color:var(--pOn)`; badge `background:var(--pg); color:#fff`
     - Items: Overview · Projects & Repositories (badge 6) · Tickets (badge 128) ‖ Claude Settings · Authentication · User Management · Integrations (badge 3) · Settings
  4. **Footer block** (`margin-top:auto`): status card (green pulsing dot + `ALL SYSTEMS NOMINAL` + `3 integrations connected · 2 agents online`), then the user chip (30 px `var(--pg)` avatar `EK`, `Emre Kaya`, `Owner · EMESOFT`).
- **Page header** (`main > header`): `display:flex; align-items:center; gap:12px; padding:14px 18px`, same glass recipe as the sidebar, `border-radius:20px`, `flex-shrink:0`. Children in order:
  1. Title block `flex:1 1 190px; min-width:0; overflow:hidden` — page title 19 px/900/-.03em with `white-space:nowrap; overflow:hidden; text-overflow:ellipsis`; subtitle 12 px `var(--faint)`, also ellipsised. **The title must be the flexible item and must truncate** — otherwise it overlaps the search field at narrow widths.
  2. Command-palette button `flex:0 1 320px; min-width:130px; margin-left:auto` — search icon, placeholder `Search projects, tickets, knowledge…`, mono `⌘K` chip.
  3. 1 px × 26 px divider `var(--bd2)`.
  4. **Claude credential chip** — pulsing status dot (green `#6ee7b7` active / amber `#fbbf24` expiring / rose `#fb7185` expired-or-missing), Claude star glyph in `#D97757`, label `Shared account` | `Personal token`, chevron. Opens the credential popover (below).
  5. **Dark/light toggle** — 38 px square, sun icon in light mode, moon in dark.
  6. **Bell** — 38 px square with a 6 px accent notification dot.
- **Scroll region**: `flex:1; min-height:0; overflow-y:auto; padding:2px 4px 20px 2px`. Every page's root is `display:flex; flex-direction:column; gap:14px; animation:fadeInUp .38s ease both`.

### 1. Landing (`view === 'landing'`)

Single column, `max-width:1400px`, `padding:22px 44px` header / `70px 44px 44px` hero.

- **Header**: 88 px-tall 3D logo with tilt + metal sheen, 1 px × 56 px divider, `Eme` + silver `Hub` at 40 px/900/-.04em; right side text links `Products`, `Platform` and a primary `Enter EmeHub →` button.
- **Hero** (centred): status pill (`EMESOFT · AI Operating Center` with pulsing dot), `h1` 80 px/900/-.05em/`line-height:1` — “One command center for every **AI agent** you run” with *AI agent* in the silver gradient; 17 px sub-paragraph, `max-width:600px`; primary `Open the hub →` + ghost `Meet the agents`.
- **Product cards** (2-up grid, gap 14): per product — 26 px glyph tile in the product gradient, name, `Live` / `Placeholder` badge, role, description, tag pills, a big metric (`1,204` / `Q4 2026`) with label, and a 3-stat row. Cards use the pointer tilt + a radial cursor-follow wash.
- **Capability grid** (3-up): icon + title + one-line description; each navigates to a page (User management → users, Claude credentials → claude, Authentication → auth, Integrations → integrations, Project knowledge → projects, Synced tickets → tickets).
- **Final CTA** and a compact footer.

### 2. Overview (`page === 'overview'`)

- Greeting row: `Good morning, Emre` 28 px/900 + one-line status; right-aligned quick actions (`Import tickets`, `Add knowledge`, `Invite member`, `New project`) as ghost chips with icons.
- 2-up **product cards** (app variant: adds `Launch` / `Preview` button).
- 4-up **KPI tiles**: value 26–30 px/900/-.04em + 9.5 px/700/.11em label.
- **Activity feed** — glass list; each row: kind chip (Q‑Agent purple, D‑Agent cyan, import/kb neutral, warn amber), text with a mono accent reference (`SUR-1428`), actor, relative time.
- **Integration strip** and **top-3 projects** summary rows.

### 3. Projects & Repositories (`page === 'projects'`)

**List state** — 3-up card grid (gap 14) + a dashed "Connect a repository" tile:
- 38 px initials tile in the project gradient, name 15 px/800, mono repo path 10.5 px `var(--faint)`.
- 3-up mini stats (cases / coverage / branch) in `var(--inset)` boxes with mono values.
- Agent tag pills (Q‑Agent `#a78bfa` @ 12% tint, D‑Agent `#67e8f9`), provider name right-aligned, `Configure` ghost button + "updated" timestamp.
- Card hover: `translateY(-3px)`, border → `var(--pb)`, background → `var(--card3)`.

**Detail state** (opened by `Configure`) — replaces the list:
- Back link `← All projects`.
- Header card: 46 px provider glyph (Azure `#0078d4` "A", Jira `#2684ff` "J", GitHub `#c9ced8` "G" on `#12121a`), name 23 px/900, agent pills, mono `repo · branch · provider`, knowledge status pill (Indexed green / Needs refresh amber / Not indexed neutral), `Refresh repository` ghost + `Re-index knowledge` primary.
- Tab row: **Overview · Project knowledge · Repository · Agents · Settings** (tab pill = `padding:9px 16px; radius:11px; 12.5px/700`; active `var(--pt)` + `var(--pb)` + `var(--pOn)`).
  - **Overview** — 4-up KPIs (tickets mirrored, agent runs, pass rate, knowledge confidence with a 6 px gradient bar) + 4-up meta row (framework, last indexed, mono knowledge version, page objects).
  - **Project knowledge** — if not indexed: dashed empty state with a book glyph and a `Build project knowledge` primary CTA (starts indexing, toasts, switches to this tab). If indexed: "What the agents learned" accordion (4 sections: Architecture & modules, Test conventions, Page objects & selectors, Environments & test data) with a chevron that rotates 90° when open; then a source toolbar (search + type chips All/Markdown/Document/URL/File + `Add source`) and a 7-column source table (icon, title+mono id, type, size, chunks, scope, state pill) with an empty state.
  - **Repository** — detected stack chips, "shared utilities the agents reuse" mono rows, 4-up counters (indexed assets, page objects, fixtures, default branch).
  - **Agents** — agents wired to this project + a note pointing at Claude Settings › Agent preferences.
  - **Settings** — **Project knowledge** summary row (status · version · last indexed) with `Open knowledge base →`, then three toggles: *Re-index on every merge to `<branch>`*, *Publish evidence back to `<provider>`*, *Block runs on a stale index*; then a 3-up read-only meta grid (provider, repository, knowledge scope).

### 4. Tickets (`page === 'tickets'`)

Mirrors the Q‑Agent ticket browser: **exactly one provider is active at a time**, and the filter set changes with it.

- **Toolbar** (single wrapping row, gap 9):
  1. **Source picker** — glyph + provider name + chevron; dropdown (250 px, `var(--pop)`, radius 13) headed `TICKET SOURCE` listing Azure DevOps / Jira Cloud / GitHub with a green check on the active one. Switching source clears all field filters.
  2. 1 px divider, then a **search field** (`flex:1; min-width:170px; max-width:250px`, placeholder `Search tickets…`).
  3. **Provider-variant filter pills**, one per schema field. Pill: `height:36px; padding:0 12px; radius:11px; 12.5px/600` + chevron; idle `var(--card2)`/`var(--bd2)`/`var(--txt4)`, set `var(--pt)`/`var(--pb)`/`var(--pOn)` and the label becomes the chosen value. Dropdown items show a green check when selected; picking the same value clears it.
     - **Azure DevOps**: Sprint (Sprint 24, Sprint 23) · Area path (`Surveyor\QA`, `Surveyor\Reports`, `Surveyor\Mobile`, `Nova\Billing`) · State (New, In progress, In review, Blocked, Done) · Work item type (User Story, Bug, Task)
     - **Jira**: Sprint (LED Sprint 12/11) · Epic (Reconciliation, Payments API, Single sign-on) · Status (same five) · Issue type (Story, Bug, Task) · Priority (Highest, High, Medium, Low)
     - **GitHub**: Milestone (v0.3, v0.4) · Label (bug, enhancement, qa) · State (New, In progress, In review, Done) · Assignee (E. Kaya, J. Novak, A. Demir)
  4. `× Clear` ghost link — visible only when any filter or the query is set; hover turns `#fb7185`.
  5. Right side: `last import 4 minutes ago` (or `pulling now…`) + primary **Import** button (download-tray icon; label becomes `Importing…` with the icon spinning while a run is in flight).
- **Table** — glass container; columns `110px | 2.4fr | 1fr | 120px | 120px | 110px | 110px`, gap 12, header row 9.5 px/700/.11em: `ID · WORK ITEM · PROJECT · STATUS · AGENT · IMPORT · OWNER`. Rows 14 px/20 px padding, 1 px `var(--bd3)` divider, hover `var(--card3)`, click → toast "read-only mirror". ID is mono 11.5 px/700 in `var(--psText)`. Status and Import are status pills; Agent is an agent pill or a neutral `Unassigned`. Empty state = magnifier glyph + "No work items match these filters". Footnote: lock icon + "Read-only mirror. Edit work items in `<provider>` — the next import reflects the change."

### 5. Import dialog (modal, opened from Tickets or the Overview quick action)

580 px wide, `var(--pop)`, radius 22, `box-shadow:0 40px 90px -20px #000`, `animation:scaleIn .22s`; scrim `rgba(6,6,10,.62)` + `blur(7px)`, `animation:fadeIn .2s`.

- **Header**: 34 px provider glyph, `Import tickets`, `Pull work items from <provider>`, close ✕.
- **Mode switch**: segmented `Basic | Advanced` in a 4 px inset track.
- **Basic** → `WHAT TO PULL` label + three radio rows (18 px ring, filled 8 px dot when on): *Active sprint* (~24 items) · *Assigned to me* (~9 items) · *All open work items* (~118 items). Selected row: `var(--pt)` + `var(--pb)`.
- **Advanced** → `FILTER BY FIELD` + a 2-column grid of the **same provider schema** as the toolbar, each a full-width dropdown showing `Any` until set. Jira adds a mono **JQL (optional)** input (`project = LED AND status != Done`); GitHub adds a mono **Search query (optional)** input (`is:issue is:open label:qa`).
- **Footer**: `Read-only pull · credentials stay encrypted`, `Cancel`, primary `Import now`. Running an import closes the dialog, spins the toolbar button for 1.5 s, then toasts `Import complete — 31 work items pulled from <provider> · <scope|field filters applied>`.

### 6. Claude Settings (`page === 'claude'`)

Tabs: **Credentials · Models · Agent preferences**, with a right-aligned `Save changes` primary.

**Credentials** (the important one — mirrors Q‑Agent's credential model):
- **Explainer banner** — Claude-terracotta gradient (`linear-gradient(135deg, rgba(217,119,87,.1), rgba(225,23,43,.05))`, border `rgba(217,119,87,.22)`), 38 px star tile, copy explaining that agents authenticate with the OAuth token inside a `.credentials.json` written to `~/.claude/.credentials.json` before each run. Inline code chips: mono 12 px, `var(--terra)` on `rgba(217,119,87,.14)`, radius 5.
- **Your Claude account** (left, 1.5fr):
  - Two **source chooser cards**: *Shared account* (people glyph, accent tint) and *Your own account* (key glyph, cyan tint). Selected card gets `var(--pt)` + `var(--pb)` and a 20 px filled check.
  - *Shared* → summary card: Claude star tile, credential label, mono email, status pill; 3-up meta (SUBSCRIPTION · TOKEN EXPIRES `12 Oct 2026 · in 76 days` · MAINTAINED BY `Workspace admin`); footnote with a padlock.
  - *Your own* → if none attached: dashed drop zone (`1.5px dashed var(--pb)`, `var(--pt)` fill) reading "Drop your `.credentials.json` — or click to browse · found at `~/.claude/.credentials.json`"; while parsing, a spinner + "Reading token…". Once attached: cyan-bordered card with mono filename, status pill, 3-up meta (subscription, expiry + days, last refreshed), **SCOPES** mono chips, **ACCESS TOKEN** row (masked `first16••••••••••••last4`, `Reveal`/`Hide`), `Replace file` + destructive `Remove & use shared`.
  - **Real file parsing**: read the dropped JSON, accept `claudeAiOauth` | `claude_ai_oauth` | the root object, require `accessToken`/`access_token`, read `expiresAt`/`expires_at` (epoch ms) → days left, `scopes`, `subscriptionType`. Invalid file → warn toast "Invalid .credentials.json / Expected a claudeAiOauth token object".
- **Right column (1fr)**: *Connection health* (green pulse row `Authenticated · 42ms` + mono `200`, `Test connection` ghost), *Usage this month* (`18.4M` tokens, 62 % quota bar, Q‑Agent/D‑Agent split), *API key fallback* (masked key + Show/Hide, "used by headless CI runners").
- **SHARED CLAUDE ACCOUNTS** (admin section, label + hairline + `ADMIN` chip). One card per shared credential:
  - Amber warning strip when expiring/expired: "This token expires in 1 day — rotate it to keep agent runs authenticated."
  - 44 px Claude tile, label 15.5 px/800, `DEFAULT` chip, mono email, status pill, ⋮ menu (`Set as default`, destructive `Remove credential`).
  - 4-up meta: SUBSCRIPTION · EXPIRES (+ days line) · LAST REFRESHED · ASSIGNED (`4 members`).
  - SCOPES chips; ACCESS TOKEN row with Reveal; source line (mono `.claude/.credentials.json · synced`) + `Rotate token` upload label.
  - Card border: default → `var(--pb)`; expiring → `rgba(251,191,36,.3)`; else `var(--bd)`.
  - Below: dashed `Add a shared Claude account` upload zone (same parser; first upload becomes default).

**Models**: default model + fast model dropdown cards, thinking-level chips (Off/Low/Medium/High) with an explanatory line, and a `Parallel agent runs` range (1–8).
**Agent preferences**: three toggles (auto-approve low-risk steps, attach evidence to the provider, stream reasoning) + Q‑Agent (`Inherited`) and D‑Agent (`Locked`) override cards.

### 7. Authentication (`page === 'auth'`)

Tabs **Single sign-on · Sessions · API keys · Login providers**: SSO card (toggle, entity id / ACS URL / verified domain / certificate meta, MFA toggle) + session policy + a `barGrow`-animated recent-sign-ins chart; sessions table with revoke; API keys table with reveal/copy; provider rows with toggles.

### 8. User Management (`page === 'users'`)

Tabs **Members · Roles · Invitations**, right-aligned `Invite member` primary.
- **Members** table — columns `36px | 1.05fr | 1.3fr | 170px | 110px | 130px`, header `MEMBER · EMAIL · CLAUDE CREDENTIAL · LAST ACTIVE · ROLE`. Credential cell = 7 px dot + label: shared → `#D97757` dot + credential name, personal → `#22d3ee` dot + `Personal token`, none → muted dot + `Not assigned`. Role cell is a badge; non-owners open a role dropdown (Owner/Admin/Member/Viewer).
- **Roles** — 2-up cards, initial badge, member count chip, description, permission checklist.
- **Invitations** — rows with dashed envelope tile, email, role chip, sent/by, `Resend` + destructive `Revoke`.

### 9. Integrations (`page === 'integrations'`)

Provider-connection manager (mirrors Q‑Agent's settings):
- Summary strip: green pulse + `3 providers · 4 connections live` + "Credentials encrypted at rest · tokens never leave EmeHub" + `Import all` ghost.
- Per provider (Azure DevOps, Jira Cloud, GitHub): 34 px glyph, name 15.5 px/800, `2 connections · 4 projects`, `+ Add connection` (accent-tint button).
- Per connection: collapsed row = chevron (rotates 90° when open), label + mono summary, status pill, `imported 2 min ago`, trash button (hover → rose). Expanded = 2-column field grid (text/password inputs, focus border `var(--pb)`) + `Test connection` (spins ~1.3 s then toasts "Connection verified … responded in 118 ms") + `Save connection` + "Credentials encrypted at rest".
  - ADO fields: Organisation URL, Project, Personal access token (password), Area path. Jira: Site URL, Account email, API token, Default JQL. GitHub: Organisation, App installation ID, Private key, Default branch.

### 10. Settings (`page === 'settings'`)

`max-width:1080px`, three glass cards.
- **Appearance** — *Interface mode* segmented Dark|Light (icon + label, active = `var(--pg)` + `#fff` + accent glow); *Brand colour* 4 swatch cards (EMESOFT Red, Agent Purple, Signal Cyan, Metallic Steel — 26 px gradient chip + label + check when active); *Ambient bloom* range 0–100 step 5 with a mono `%` readout; *3D constellation field* toggle (tears down / re-creates the WebGL scene); *Depth on hover* toggle (gates all pointer tilt).
- **Workspace defaults** — three rows (label + description + chip group): Default provider (Azure DevOps / Jira / GitHub), Default agent (Q‑Agent / D‑Agent / None), Knowledge scope (Per project / Workspace).
- **Notifications** — three toggle rows: Failed imports, Credential expiry, Every agent run.

### Overlays

- **Command palette** (`⌘K` / `Ctrl+K`, or the header search): scrim `rgba(6,6,10,.62)` + `blur(6px)`, panel `var(--pop)` at 12 vh, input row + grouped results (pages, projects, actions), `Esc` closes.
- **Claude credential popover** (header chip): 330 px, model name + source + `Admin-managed`/`Your token`, status pill, `CREDENTIAL` mono name, `Token expires <date · in N days>`, segmented `Shared | Personal`, `Manage Claude credentials` → Claude Settings.
- **Modals**: New project, Invite member, Add knowledge, New API key, Integration settings — 520 px, `var(--pop)`, radius 20, `animation:fadeInUp .25s`.
- **Toast**: bottom-centre, `left:50%` + `translateX(-50%)`, `animation:toastIn .34s cubic-bezier(.2,.7,.3,1)`, glass pill with a 30 px status ring (`ring` pulse), title + body, auto-dismiss after **3200 ms**, kinds `ok | warn | info`.

---

## Interactions & Behavior

### Navigation
- Landing ⇄ app: `Enter EmeHub` / `Open the hub` → app (Overview); sidebar logo → landing.
- Sidebar sets `page` and resets the scroll container to `scrollTop = 0`.
- Projects list → detail via `Configure` (sets `projectId`, tab `overview`, resets scroll); `← All projects` clears it.
- Every dropdown/popover closes on scrim click, `Esc`, and when another one opens.

### Motion — CSS keyframes (define once, globally)

| Name | Definition | Used for |
|---|---|---|
| `fadeInUp` | `from{opacity:0;transform:translateY(16px)} to{opacity:1;transform:none}` | every page/section entrance, `.38s ease both` (modals `.25s`) |
| `fadeIn` | `opacity 0→1` | scrims, `.2s` |
| `scaleIn` | `from{opacity:0;transform:scale(.96)}` | dropdowns/popovers `.15s`, dialogs `.22s`; `transform-origin` set to the trigger corner |
| `slideIn` | `from{opacity:0;transform:translateX(14px)}` | drawer content |
| `glowPulse` | `0%,100%{opacity:.45} 50%{opacity:.85}` | the two ambient blooms, 9 s and 11 s (1 s delay) |
| `floaty` | `0%,100%{translateY(0)} 50%{translateY(-9px)}` | decorative hero float |
| `pulseDot` | `0%,100%{opacity:1;scale(1)} 50%{opacity:.4;scale(.82)}` | all live status dots, 1.7–2.4 s |
| `spin` | `to{rotate(360deg)}` | spinners: `.7s` (upload), `.8s` (test/import), `.9s` (indexing) |
| `metalFlash` | `0%{translate(150%,-150%) rotate(45deg);opacity:0} 12%{opacity:.85} 55%{translate(-160%,160%);opacity:.85} 68%,100%{opacity:0}` | the diagonal sheen sweeping the 3D logo — `7.5s ease-in-out infinite 2s` on a 60 %-wide gradient span, **`opacity:0` base + `animation-fill-mode:backwards`** so nothing shows during the 2 s delay |
| `sheen` | `background-position -380px → 380px` | skeleton shimmer |
| `toastIn` | `0%{translate(-50%,26px) scale(.96)} 60%{translate(-50%,-3px) scale(1.005)} 100%{translate(-50%,0) scale(1)}` | toast entrance |
| `toastBar` | `scaleX(1) → scaleX(0)` | toast countdown bar |
| `barGrow` | `scaleY(.04) → scaleY(1)` | chart bars |
| `ring` | `0%{scale(.6);opacity:.7} 100%{scale(2.2);opacity:0}` | toast status ring |

### Motion — pointer-driven (JS)
- **Logo tilt**: on `mousemove` over the logo wrapper (`perspective:820px`), set `transform: perspective(820px) rotateX((0.5-py)*16deg) rotateY((px-0.5)*24deg) scale(1.06)`, where `px/py` are normalised cursor coords inside the element; `transition: transform .35s cubic-bezier(.2,.7,.3,1)`. On leave, reset to `rotateX(0) rotateY(0) scale(1)`.
- **Card tilt**: `perspective(1100px) rotateX((0.5-py)*9deg) rotateY((px-0.5)*11deg) translateY(-5px)` plus CSS vars `--gx/--gy` (cursor %, drives a radial highlight wash). Reset on leave.
- Both are gated by the **Depth on hover** setting.

### Motion — transitions (0.15–0.35 s)
`background .18–.2s` on rows/buttons/nav, `transform .18s` on primary buttons (`translateY(-1px|-2px)`), `border-color .2s` on inputs/cards, `transform .2s` + `border-color .2s` on cards (`translateY(-3px)`), `transform .22s` on accordion/connection chevrons (`rotate(90deg)`), `left .22s cubic-bezier(.2,.7,.3,1)` on toggle knobs.

> ⚠️ **Prototype caveat:** in the preview runtime CSS transitions did not advance, so the shipped prototype has the knob `left` transition and the theme-token transitions **removed** to guarantee correct end states. In a real browser, restore them: knob `left .22s cubic-bezier(.2,.7,.3,1)`, and `background/border-color/color .2s` on theme-token-driven surfaces (a ~.35 s cross-fade on `body` when the mode flips is a nice touch).

### Async behaviours (all fake-timed in the prototype; wire to real requests)
| Action | Feedback | Duration |
|---|---|---|
| Import now | button label → `Importing…` + spinning icon, then success toast | 1500 ms |
| Test connection | button label → `Testing…` + spinner, then sets the connection `Connected` / `just now` and toasts | 1300 ms |
| Credential upload | drop zone → spinner + `Reading token…`, then card appears + toast | 850 ms after parse |
| Build knowledge | switches to the knowledge tab, marks the project indexed, toasts `Indexing started` | immediate |
| Mode / accent change | applies tokens immediately + toast | immediate |

### Keyboard
`⌘K` / `Ctrl+K` toggles the palette; `Esc` closes palette, popovers, dropdowns and modals.

### 3D constellation (background)
three.js (r128 in the prototype), `WebGLRenderer({alpha:true, antialias:true})`, `setPixelRatio(min(dpr,2))`, `PerspectiveCamera(60, w/h, 1, 4000)` at `z = 660`.
- **62 nodes** (40 when `prefers-reduced-motion`) randomly inside 1060 × 660 × 740; `PointsMaterial({size:5.6, opacity:.9, vertexColors:true, depthWrite:false})`.
- **Edges** between any pair closer than 250 units; `LineBasicMaterial({opacity:.45, vertexColors:true})`.
- **1050 dust particles** (500 reduced) in 2600 × 1700 × 1400; `size:4`, twinkling opacity `0.4 + 0.32·world`.
- Node/dust colour cycles through `[accent, silver, steel]`; nodes brighten toward the cursor (projected distance → `act` easing at `0.2`), plus a slow global “breathe”.
- Camera drifts toward the cursor (`x ±? · .03` lerp); group rotates slowly.
- **Theme-aware**: dark → `AdditiveBlending`, silver `0xdfe4ec`, steel `0x7a8290`, lines `0x8d97a8`. Light → `NormalBlending`, silver `0x6b7280`, steel `0x99a1b2`, lines `0x5a6472`, node opacity `.72`, line opacity `.26`, dust `.22 + .18·world`.
- Accent changes swap the accent colour live; the Settings toggle disposes the renderer and clears the container, and re-creates it when switched back. Always dispose on unmount and remove the `mousemove`/`resize` listeners.

### Responsive
Desktop-only design (≥1280 px comfortable). Known constraints if you must go narrower: the header must let the title truncate first; tables need horizontal scroll below ~1100 px; the 3-up grids should collapse 3→2→1; the sidebar should become an overlay drawer under ~1024 px. Mobile layouts are **not** designed — ask before inventing them.

---

## State Management

Single view-model (prototype uses one component's state). Grouped by concern:

- **Shell**: `view: 'landing'|'app'`, `page`, `paletteOpen`, `paletteQuery`, `modal`, `dd` (open dropdown key), `drawer`, `toast`, `themeOpen`.
- **Appearance**: `mode: 'dark'|'light'`, `accent: 'red'|'purple'|'cyan'|'steel'`, `ambient: 0–100`, `fx3d: boolean`, `tilt: boolean`.
- **Workspace defaults**: `defProvider`, `defAgent`, `defScope`.
- **Notifications**: `notifImport`, `notifCred`, `notifRuns`.
- **Projects**: `projectId`, `projTab: 'overview'|'knowledge'|'repos'|'agents'|'settings'`, `builtKnowledge: string[]`, `openSections: {}`, `knowFilter`, `knowQuery`, `pjAutoIndex`, `pjEvidence`, `pjBlockUnindexed`.
- **Tickets**: `ticketSource: 'ado'|'jira'|'gh'`, `tkFilters: {field: value}`, `fMenu`, `ticketQuery`.
- **Import**: `importOpen`, `importMode: 'basic'|'advanced'`, `importScope: 'sprint'|'assigned'|'all'`, `impFilters`, `impMenu`, `importJql`, `importing`.
- **Claude**: `credSource: 'shared'|'personal'`, `personalCred | null`, `sharedCreds[]` (id, label, email, sub, expDisplay, daysLeft, scopes, lastRefreshed, members, isDefault, token, source), `revealed: {}`, `credMenu`, `uploadingPersonal`, `uploadingShared`, `claudeOpen`, `mainModel`, `fastModel`, `thinking`, `prefAuto`, `prefEvidence`, `prefStream`, `prefParallel`, `apiKey`, `showKey`.
- **Integrations**: `expandedConn`, `connFields: {'<connId>.<field>': value}`, `testingConn`.
- **Auth/users**: `ssoOn`, `mfaOn`, `sessionRevoked[]`, `keyRevealed`, `tabAuth`, `tabUsers`, `roleEdits: {email: role}`, `inviteEmail`, `inviteRole`.

Derived rules worth preserving: credential **status** = `daysLeft == null ? Active : <0 Expired : ≤2 Expiring : Active`; the **default** shared credential is `isDefault` (fallback: first); switching to *personal* with nothing attached navigates to Claude Settings › Credentials and prompts an upload; ticket filtering is `provider match && every set field equals the ticket's field && query matches id|title|project`.

### Data fetching (production)
`GET` projects, tickets (per provider + filters), knowledge sources per project, shared credentials, provider connections, members/roles/invites, sessions/API keys. `POST` import run, test connection, save connection, credential upload/rotate/remove/set-default, build/re-index knowledge, role change, invite.

---

## Design Tokens

### Theme tokens (CSS custom properties on `:root`; the whole light mode depends on these)

| Token | Dark | Light |
|---|---|---|
| `--bg` | `#0a0a0f` | `#eef0f5` |
| `--panel` | `rgba(20,20,28,.55)` | `rgba(255,255,255,.74)` |
| `--card` | `rgba(255,255,255,.035)` | `rgba(255,255,255,.66)` |
| `--card2` | `rgba(255,255,255,.045)` | `rgba(255,255,255,.82)` |
| `--card3` (hover/fill) | `rgba(255,255,255,.05)` | `rgba(18,22,36,.05)` |
| `--inset` | `rgba(255,255,255,.03)` | `rgba(18,22,36,.035)` |
| `--bd` | `rgba(255,255,255,.07)` | `rgba(18,22,36,.1)` |
| `--bd2` | `rgba(255,255,255,.09)` | `rgba(18,22,36,.14)` |
| `--bd3` | `rgba(255,255,255,.06)` | `rgba(18,22,36,.075)` |
| `--pop` | `#191921` | `#ffffff` |
| `--code` | `rgba(8,8,13,.6)` | `rgba(18,22,36,.05)` |
| `--txt` | `#ECECF1` | `#141721` |
| `--txt2` | `#dcdce4` | `#252935` |
| `--txt3` | `#c3c3d0` | `#414759` |
| `--txt4` | `#a9a9bc` | `#565d70` |
| `--muted` | `#8b8b9e` | `#6a7182` |
| `--faint` | `#7a7a8c` | `#5f6675` |
| `--label` | `#6c6c7e` | `#5c6371` |
| `--shadow` | `rgba(0,0,0,.6)` | `rgba(18,22,36,.16)` |
| `--bloom2` | `rgba(150,160,180,.2)` | `rgba(120,135,165,.16)` |
| `--scroll` / `--scroll2` | `rgba(255,255,255,.09)` / `.18` | `rgba(18,22,36,.16)` / `.3` |
| `--brandSoft` (purple text) | `#c4b5fd` | `#5b3fc4` |
| `--cyanSoft` (cyan text) | `#a5f3fc` | `#0d6a7a` |
| `--terra` (Claude text) | `#e0a58c` | `#a2542f` |
| `--silver` | `linear-gradient(135deg,#fff 0%,#cfd4dd 30%,#8f95a1 48%,#f4f6f9 62%,#a9afba 100%)` | `linear-gradient(135deg,#3f4759 0%,#7b8496 34%,#2f3644 52%,#8d95a6 70%,#454d5f 100%)` |

**Contrast rule that must survive the port:** any pale hue used as *foreground text* needs a darkened light-mode counterpart (all the tokens above are ≥4.5:1 on their surface). Semantic pill colours are darkened through a map: `#6ee7b7→#0b6d4c`, `#fbbf24→#8a5b00`, `#fb7185→#a5123c`, `#a5f3fc/#67e8f9→#0d6a7a`, `#c4b5fd/#a78bfa→#5b3fc4`, `#c3cad6→#4a5162`, `#8b8b9e→#5c6273`; pill tint alpha goes to `.15` (white tints become `rgba(18,22,36,.07)`).

### Accent tokens (set per accent on the app root)

| Accent | `--p` | `--pl` | `--ps` | `--pg` | `--pglow` | `--pt` | `--pb` | `pDark` (light text) | three.js hex |
|---|---|---|---|---|---|---|---|---|---|
| EMESOFT Red (default) | `#e1172b` | `#ff5568` | `#ffa1ab` | `linear-gradient(135deg,#ff4d5c,#c20d22)` | `rgba(225,23,43,.5)` | `rgba(225,23,43,.14)` | `rgba(225,23,43,.34)` | `#a80d1e` | `0xe1172b` |
| Agent Purple | `#8b5cf6` | `#a78bfa` | `#c4b5fd` | `linear-gradient(135deg,#8b5cf6,#6366f1)` | `rgba(139,92,246,.5)` | `rgba(139,92,246,.14)` | `rgba(139,92,246,.34)` | `#5227b8` | `0x8b5cf6` |
| Signal Cyan | `#22d3ee` | `#67e8f9` | `#a5f3fc` | `linear-gradient(135deg,#22d3ee,#0ea5b7)` | `rgba(34,211,238,.45)` | `rgba(34,211,238,.13)` | `rgba(34,211,238,.32)` | `#0b5c69` | `0x22d3ee` |
| Metallic Steel | `#9aa3b2` | `#c3cad6` | `#dde2ea` | `linear-gradient(135deg,#e2e6ec,#8d939e)` | `rgba(180,190,205,.4)` | `rgba(180,190,205,.13)` | `rgba(180,190,205,.3)` | `#434a59` | `0xb4becd` |

Derived: `--pOn` (text on an accent tint) = `#fff` dark / `pDark` light. `--psText` (accent text on a surface) = `--ps` dark / `pDark` light.

### Semantic status colours (dark values; darken per the map above in light mode)

`Done/Passed/Imported/Indexed/Connected/Active` `#6ee7b7` on `rgba(16,185,129,.13–.14)` · `In progress/Importing/Pending/Attention/Expiring` `#fbbf24` on `rgba(251,191,36,.13–.14)` · `Blocked/Failed/Expired` `#fb7185` on `rgba(244,63,94,.14)` · `In review` `#a5f3fc` on `rgba(34,211,238,.13)` · `New/Paused` `#c3cad6`/`#8b8b9e` on `rgba(255,255,255,.07)`.
Brand/provider: Claude `#D97757`, Azure DevOps `#0078d4`, Jira `#2684ff`, GitHub `#c9ced8` (glyph `#12121a`), Q‑Agent `#a78bfa`, D‑Agent `#67e8f9`.

### Typography
- **UI/display**: **Satoshi** (Fontshare, weights 400/500/700/900) → fallback `'Segoe UI', system-ui, sans-serif`.
- **Mono**: **JetBrains Mono** (400/500/600) for IDs, tokens, paths, keyboard hints, metrics, timestamps.
- Ramp: hero `80/900/-.05em` · page h1 `28/900/-.035em` · detail h1 `23/900/-.035em` · header title `19/900/-.03em` · card title `15/800/-.01em` · section title `13.5–14.5/700–800` · body `12.5–13.5/500–600`, `line-height 1.5–1.65` · meta `11–12/500–600` · uppercase label `9–10.5/700`, `letter-spacing .09–.12em` · mono id `10–12.5/600–700`.
- `text-wrap: pretty` on paragraphs, `balance` on the hero.

### Spacing, radius, elevation
- Shell `padding:14px`, `gap:14px`; card padding 16–22; grid/stack gaps 8–14 (use flex/grid `gap`, never margin runs).
- Radius: pill 20 · small control 7–11 · button 11–14 · card 16–22 · panel 20–22 · glyph tile 7–14.
- Shadows: panels `0 24px 60px -20px var(--shadow)`; popovers `0 24px 60px -18px rgba(0,0,0,.8)`; dialogs `0 40px 90px -20px #000`; primary buttons `0 8px 20px -6px var(--pglow)`.
- Glass recipe: `background:var(--card); backdrop-filter:blur(22px); border:1px solid var(--bd)` (panels use `--panel` + `blur(28px)`).
- Scrollbars: 10 px, transparent track, `var(--scroll)` thumb with a 2 px transparent border and `background-clip:padding-box`.

---

## Assets

- `app/public/assets/eme-3d-logo-cut.png` — EMESOFT 3D logo (red infinity mark + `emesoft` wordmark + “Emerging your Business”), transparent PNG. Rendered 88 px tall on the landing header, full sidebar width in the app. **Lives in the app, not in this bundle** — it is served from the Vite public root as `/assets/eme-3d-logo-cut.png`. The prototype HTML references it as `../../app/public/assets/…`.
- All other iconography is inline SVG, Feather/Lucide style: `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width:2–2.6`, round caps/joins, rendered 12–22 px. The Claude mark is a filled 5-point star in `#D97757`. No raster icons, no icon font, no illustrations.
- Fonts load from `https://api.fontshare.com` (Satoshi) and Google Fonts (JetBrains Mono) — self-host in production.
- three.js r128 is loaded from a CDN in the prototype — install it as a dependency instead.

## Files

- `EmeHub.dc.html` — the full prototype (landing + all 8 app pages + overlays). Open directly in a browser.
- `support.js` — prototype runtime (rendering harness only, **not** part of the design; do not port).
- `../../app/public/assets/eme-3d-logo-cut.png` — brand mark. Kept in the app rather than duplicated here; the prototype loads it by that relative path.
- `Q-Agent-DESIGN_SYSTEM.md` — the written design system this UI extends (foundations, components, motion, voice).
- `Q-Agent.ref.html` — the sibling product (Q‑Agent) whose credential, provider-connection and ticket-filter behaviour EmeHub mirrors. Useful when a detail is ambiguous.

### Reading the prototype
The single file is ordered: `<helmet>` (fonts, `:root` tokens, `@keyframes`) → background layers → landing view → app shell (sidebar, header, one block per page) → overlays (palette, import dialog, modals, toast) → the logic class (data tables, handlers, then one big view-model builder, then the three.js scene). Search for the `<!-- ============ NAME ============ -->` comments to jump to a page.

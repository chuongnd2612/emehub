# ADR 0006 — Implementing the EmeHub design handoff

- **Status:** Accepted
- **Date:** 2026-07-29
- **Supersedes:** [ADR 0004](0004-inherit-the-q-agent-design-system.md)

## Context

A complete, high-fidelity design for EmeHub was delivered in
`design/design_handoff_emehub/`: a written spec (`README.md`), a working HTML prototype
(`EmeHub.dc.html`, 3,105 lines), the Q-Agent design system it extends, and the Q-Agent
prototype for cross-reference. It covers a landing view plus eight app pages, overlays, a full
light/dark theme system, four selectable accents and a WebGL background.

[ADR 0004](0004-inherit-the-q-agent-design-system.md) assumed the new design would be a
refresh within the existing language. It is not — it contradicts that ADR in three specifics.

## Decision

The handoff is binding. `README.md` is the spec; `EmeHub.dc.html` is a reference to *look at*,
not code to copy; `support.js` is the prototype's harness and is never ported.

### What changes from ADR 0004

| ADR 0004 said | The handoff says | Resolution |
|---|---|---|
| Brand is purple→indigo; **no accent outside** purple/indigo/cyan + semantic | Four accents — **EMESOFT Red `#e1172b` (default)**, Agent Purple, Signal Cyan, Metallic Steel — switchable at runtime | Handoff wins. Accent is a user setting on the app root. |
| Dark only | Full light mode with a mandatory contrast-darkening map | Handoff wins. Light mode is a first-class requirement. |
| Inline styles, no CSS classes | Use the codebase's own styling conventions; keep only the CSS-variable theme layer | Handoff wins. Tailwind utilities bound to CSS custom properties. |

The inline-style rule in the Q-Agent system exists because the tool that produced those
prototypes streams markup and needed styles to paint immediately. That constraint does not
apply to a real application, and the handoff says so explicitly.

### Implementation choices

**Stack** — React 19 + Vite 6 + TypeScript 5.7 + Tailwind 4, per
[ADR 0002](0002-stack-fastapi-react-mirroring-q-agent.md). Plus `react-router-dom` 7,
`zustand` for the view-model, `three` for the constellation, `cmdk` for the palette, and
`lucide-react` only where a glyph matches Feather exactly.

**Tokens are CSS custom properties named exactly as the handoff names them** — `--bg`,
`--panel`, `--card`/`2`/`3`, `--bd`/`2`/`3`, `--pop`, `--txt`…`--txt4`, `--muted`, `--faint`,
`--label`, `--p`/`--pl`/`--ps`/`--pg`/`--pglow`/`--pt`/`--pb`, `--pOn`, `--psText`, `--silver`,
`--terra`. Mode switches via `[data-mode]`, accent via `[data-accent]`, both on the app root.

They are *not* renamed to Tailwind-idiomatic names. The handoff's tables, the prototype and
any future design revision all speak these names; a translation layer would mean every future
change requires a mapping step, and mapping steps rot.

**No raw colours in components.** Tailwind's `@theme` exposes the tokens as utilities, so a
component writes `bg-card` / `text-muted`, never a hex. A hex in a `.tsx` file is a bug.

**No backend exists yet.** Every screen wires to a typed stub layer at `app/src/data/`, shaped
like the handoff's *Data fetching* section, holding the prototype's fixture data. Swapping a
stub for a real call is then a one-file change per resource. Nothing invents an API route
silently.

## Consequences

**Good.** One token layer drives light/dark and four accents with no per-component branching.
The spec is precise enough — exact pixel values, timings and easing curves — that
implementation is largely mechanical, which is what makes it safe to parallelise across
agents. Keeping the handoff in the repo means the next person has the source of truth, not a
description of it.

**Bad.** Divergence from Q-Agent. Q-Agent is dark-only, purple, inline-styled; the hub is
neither. Until Q-Agent adopts this system the suite looks like two products — precisely what
[ADR 0004](0004-inherit-the-q-agent-design-system.md) set out to prevent. Accepted as
temporary: the hub is now the canonical home of the design language, and Q-Agent should adopt
it. That is a Q-Agent issue, not a hub one.

**Bad.** Two copies of the Q-Agent design system now exist (`design/DESIGN_SYSTEM.md` and
`design/design_handoff_emehub/Q-Agent-DESIGN_SYSTEM.md`). The handoff copy is the one the spec
references; the standalone copy should be deleted once nothing points at it.

**Watch.** The prototype removed two CSS transitions because its preview runtime did not
advance them. Those must be **restored** in the real build — the toggle knob's `left` and the
theme-token cross-fade. Copying the prototype faithfully would ship the workaround, not the
design.

**Deferred.** Mobile. The design is desktop-only (≥1280 px comfortable) and the handoff says
to ask before inventing narrow layouts. The known degradation path is recorded in
[CLAUDE.md](../../CLAUDE.md); nothing is built against it yet.

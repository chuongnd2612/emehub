# ADR 0004 — Inherit the QAgent design system

- **Status:** Accepted
- **Date:** 2026-07-28

## Context

QAgent has a documented design language — dark, glassmorphic, purple→indigo brand with a cyan
highlight, Satoshi for UI and JetBrains Mono for anything that is an id, a number or code.
It is written down in `q-agent/design/DESIGN_SYSTEM.md`, extracted from shipping components
rather than invented up front, and it is what users already associate with EMESOFT's agents.

A landing-page mockup for the hub itself already exists —
`q-agent/design/EmeHub.dc.html` — built in that language: hero, suite grid (QAgent live,
BAgent and DEVAgent coming), a six-step "how the hub works" strip, and a roadmap band.

The hub is the front door. If it looks like a different product from the agents it launches,
the "one workspace" premise is undermined at the first screen.

## Decision

Copy `DESIGN_SYSTEM.md`, `EmeHub.dc.html` and the brand assets into `emehub/design/` and treat
that document as binding for the hub's UI.

Concretely, the constraints that carry over:

- Dark base (`#0a0a0f`) with ambient radial blooms; depth from blur and soft shadow, never
  from flat opaque panels.
- Brand purple `#8b5cf6` → indigo `#6366f1`, cyan `#22d3ee` as the secondary highlight.
  Semantic green / amber / rose for status. **No accent hues outside that set.**
- Satoshi for UI, JetBrains Mono for ids, metrics, timestamps and code.
- Radius, spacing and elevation scales as documented.
- Purposeful micro-motion: one intentional animation per element.
- No emoji in UI. No hand-drawn illustration.

Where the hub needs a component QAgent does not have, it is designed *in* this language and
the shared document is updated — the hub does not fork the system.

## Consequences

**Good.** Visual continuity across the suite. QAgent's auth and settings screens — which the
hub is inheriting as code anyway ([ADR 0002](0002-stack-fastapi-react-mirroring-q-agent.md)) —
arrive already on-brand. The landing page has a concrete reference implementation.

**Bad.** Two copies of `DESIGN_SYSTEM.md` now exist, in `q-agent/design/` and `emehub/design/`,
and they will drift. Accepted for now; the hub becoming the canonical home of the design
system is the obvious eventual fix, once the hub is real enough to be the reference.

**Note.** The visual design is being reworked and a new one will be supplied. This ADR
commits to *inheriting a single shared language*, not to the specific tokens in today's file.
When the new design lands it replaces `design/DESIGN_SYSTEM.md` here and the decision stands
unchanged — including for QAgent, which should then adopt it rather than diverge.

**Also inherited** (from QAgent's `CLAUDE.md`, hard-won and worth restating): portal floating
overlays to `document.body` with fixed positioning, because ancestor `backdrop-filter`,
`transform` and `filter` create stacking contexts that trap `z-index`; never put
`backdrop-filter` on a panel layered over animated content; when portalling a Framer Motion
element, `AnimatePresence` must be the direct parent of the animating child.

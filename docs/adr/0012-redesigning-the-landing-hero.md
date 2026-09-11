# ADR 0012 — Redesigning the landing hero

- **Status:** Accepted
- **Date:** 2026-09-11
- **Amends:** [ADR 0006](0006-implementing-the-emehub-design-handoff.md) — narrows "the handoff
  is binding" for §1 of the spec only
- **Amends:** `design/design_handoff_emehub/README.md` § *Screens / Views* → *1. Landing*

## Context

The landing view was built exactly as the handoff specifies: a full-width header carrying an
88 px 3D logo, a 1×56 divider and a 40 px wordmark, then a centred hero — status pill, 80 px
`h1`, sub-paragraph, two buttons — over the ambient background stack.

It is faithful, and it reads as static. The header lockup occupies roughly a third of the
canvas width before a single word of the pitch, and the centred hero leaves the right half of
the fold carrying nothing but background. The page is the first thing anyone sees of the
suite, and it undersells a product whose app shell is considerably more alive than its front
door.

The prompt that triggered this work is a "liquid glass" hero spec written for a different
product — *Taskly*, a B2C task manager: white ground, `#0084FF` primary, Fustat/Inter, a
purple orb `.webm` hotlinked from `future.co` and colour-graded to blue with a CSS filter,
customer-count social proof, a logo wall. Read as a direction it is wrong for EmeHub. Read as
a **catalogue of layout and surface techniques** it contains three things worth taking: the
two-column hero, the floating pill navbar, and the inner-highlight treatment that makes a
surface read as glass.

## Decision

**The landing keeps its ground and changes its composition.** Dark stays, the WebGL
constellation stays, the two `glowPulse` blooms stay, EMESOFT Red stays the default accent.
What changes is the arrangement of the fold and the material the chrome is made of.

### 1. Glass is a surface recipe, not a blur

A glass surface is a semi-opaque background, a 1 px stroke, and an **inner highlight** along
the top edge (`box-shadow: inset 0 4px 4px …`). That third element is what actually sells the
material; the blur is optional and, here, forbidden.

`backdrop-filter` is **not** used. Two independent reasons, both already written into
[CLAUDE.md](../../CLAUDE.md): a `backdrop-filter` layered over animated content — and the
constellation is animating behind every pixel of this page — produces compositing artifacts;
and the filter creates a stacking context that traps the `z-index` of anything a descendant
tries to float. The pill navbar is precisely the element that will one day want a dropdown
under it.

The recipe becomes tokens (`--glass`, `--glass-bd`, `--glass-hi`, `--glass-shadow`) and a
`.glass-surface` utility, defined per mode — the highlight alpha is far lower on dark than the
`.25` a white ground wants. No component writes the values itself.

### 2. A floating pill navbar

Sticky at `top:30px`, centred, `width:fit-content`, radius 16, built from `.glass-surface`.
The 88 px logo shrinks to a ~28 px mark and the 40 px wordmark comes down with it; the links
and the primary `Enter EmeHub →` button are unchanged. This hands the fold back to the hero.

### 3. A two-column hero

Content left — status pill, `h1`, sub-paragraph, `Open the hub →` + `Meet the agents` — and
the orb right, bleeding slightly past the column. The `h1` comes down from 80 px to ~72 px to
sit in half the width. Below ~1024 px it returns to one column.

**Copy does not change.** The handoff says copy is final and nothing here gives a reason to
reopen it.

### 4. A WebGL orb carrying the EMESOFT mark

The right column holds a glass sphere with the EMESOFT mark inside it: a fresnel rim in the
current accent, the existing `eme-3d-logo-cut.png` as the inner element, an orbiting particle
ring, slow rotation and pointer parallax.

`three@0.171.0` is already a dependency — the constellation runs on it — so this adds no
package. It follows the same shape as `app/src/components/background/`: a framework-free scene
factory returning a `{ setAccent, setMode, dispose }` handle, a `palette.ts` holding the scene
hex values (WebGL cannot read CSS custom properties; that file is the documented exception to
"no raw colours"), and a thin React component owning nothing but lifecycle. Pointer parallax
is gated by the *Depth on hover* setting, `prefers-reduced-motion` stills it, and a missing
WebGL context degrades to no orb with the hero still fully legible.

## Alternatives rejected

Each of these is a line from the source prompt, and each is rejected for a reason that
outlives this ADR.

- **White ground, `#0084FF` primary.** Contradicts [ADR 0006](0006-implementing-the-emehub-design-handoff.md):
  the brand is EMESOFT Red `#e1172b` and the product is dark-first with light as a mandatory
  mode, not a light product with a dark mode. Adopting the prompt's palette would mean
  rewriting the token layer for one screen and leaving the other nine on the old one.
- **Fustat and Inter.** Fonts are self-hosted, no CDN. Satoshi (400/500/700/900) and JetBrains
  Mono are already in `app/public/fonts/`; adding two more families to serve one screen buys
  nothing the existing pair does not already do.
- **`backdrop-blur-[50px]` on the navbar.** See *Decision § 1*. The prompt is describing a page
  with a static gradient behind it; ours moves.
- **The `future.co` orb `.webm`.** Three independent objections. It is a third party's asset
  hotlinked from their origin — a licensing question and a runtime dependency on someone
  else's uptime. The prompt's own technique for recolouring it, `mix-blend-screen` plus
  `hue-rotate(-55deg) saturate(250%)`, is a filter chain applied to a video because the source
  colour is wrong, which is a workaround rather than a design. And `mix-blend-screen` against
  a white ground erases the element entirely — **light mode is mandatory**, so the video
  approach cannot ship in half of the product's states. A token-driven WebGL object is the
  only option that survives both themes and all four accents.
- **"Rated 4.9/5 by 2700+ customers" and a five-logo trust wall.** EmeHub is an internal
  platform for the EMESOFT agent suite. There is no customer count, no rating, and no
  third-party logos we are entitled to display. Inventing them would be fabricated social
  proof on the product's front page.
- **A 1600 px canvas.** The design canvas is 1512 × 950 and the landing container is 1400 px.
  Widening one screen desynchronises it from the other nine for no gain.

## Consequences

**Good.** The fold does more work: the pitch reads at the left edge where the eye starts, and
the right half carries a branded object instead of empty background. The glass recipe becomes
a shared primitive rather than a per-component invention, which is what stops a hex from
landing in a `.tsx`. The orb reuses an asset and a dependency the repo already carries.

**A second WebGL context on the landing route.** The constellation is global and the orb is
hero-scoped, so the landing view now runs two renderers. Both are pixel-ratio-capped and both
dispose properly, but this is the page's performance ceiling and the place to look first if it
regresses. The orb is the one that can be dropped — it is decorative and already has a
no-context path.

**The handoff and the build now disagree about §1.** That is deliberate, and it is why this
ADR exists rather than a silent edit: `design/design_handoff_emehub/README.md` § 1 is amended
in the same change to describe what was actually built, with a pointer here for the reasoning.
`EmeHub.dc.html` still shows the centred hero and is now, for this one screen, a historical
reference.

**[ADR 0006](0006-implementing-the-emehub-design-handoff.md) is not superseded.** "The handoff
is binding" remains the rule for the app shell and all eight app pages. This ADR is a
deliberate, scoped amendment to one screen of the spec — not a licence to redesign the rest by
preference. Any further departure needs its own ADR and its own reason.

**Watch.** The mark inside the orb is EMESOFT Red regardless of the selected accent, because
it is a brand mark rather than a themed element; only the fresnel rim follows the accent. If
that reads as a clash under Signal Cyan or Metallic Steel, the fix is a decision about the
brandmark, not a colour tweak in the scene.

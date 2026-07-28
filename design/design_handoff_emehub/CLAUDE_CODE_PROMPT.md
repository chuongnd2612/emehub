# Paste this into Claude Code

Put the whole `design_handoff_emehub/` folder in your repo (e.g. `docs/design/emehub/`), then start a Claude Code session in the repo root and paste the prompt below.

---

## The prompt

```
I'm implementing a new UI called EmeHub. The complete design spec is in
docs/design/emehub/.

Read these first, in this order:
1. docs/design/emehub/README.md          — the full spec: screens, components,
                                            tokens, animations, state
2. docs/design/emehub/EmeHub.dc.html      — the working HTML prototype. Open it
                                            in a browser to see the real motion
                                            and interactions.
3. docs/design/emehub/Q-Agent-DESIGN_SYSTEM.md — the design system it extends

Important:
- The HTML file is a DESIGN REFERENCE, not code to copy. Recreate it in THIS
  codebase using our existing framework, component library, routing and styling
  conventions.
- Ignore support.js entirely — it's the prototype's rendering harness.
- All data in the prototype is hard-coded. Wire it to our real APIs; where an
  endpoint doesn't exist yet, stub it behind a typed data layer and tell me.
- Keep the CSS-custom-property theme layer exactly as specified — the light/dark
  mode implementation depends on it. Both palettes are in the README's
  "Design Tokens" table.
- Reproduce the animations from the README's Motion tables (@keyframes,
  pointer-driven tilt, transitions, async feedback timings). The prototype has a
  few transitions removed for tool-specific reasons — the README says which ones
  to restore.

Before writing code:
1. Tell me which framework/libraries you'll use and how you'll map the design
   tokens into them.
2. Propose a file/component breakdown and a build order.
3. Flag anything in the spec that conflicts with our existing patterns.

Then implement one screen at a time, starting with the app shell (sidebar +
header + theme system), and stop after each for review.
```

---

## If you'd rather go screen by screen

Same setup, then for each screen:

```
Implement the <Tickets> screen from docs/design/emehub/README.md
(section "4. Tickets"). Match the layout, tokens, states and motion exactly.
The provider-variant filter schema and the Import dialog behaviour are
specified in that section and in section 5 — mirror them precisely.
Reference EmeHub.dc.html for anything ambiguous.
```

Screens: `0. App shell` · `1. Landing` · `2. Overview` · `3. Projects & Repositories` · `4. Tickets` · `5. Import dialog` · `6. Claude Settings` · `7. Authentication` · `8. User Management` · `9. Integrations` · `10. Settings` · `Overlays`.

## Tips

- **Build the shell and the token layer first.** Every screen depends on the theme tokens and the sidebar/header frame; getting them right makes the rest mechanical.
- **Have Claude Code open the prototype.** Motion is much easier to copy from the live file than from prose — tell it to run a local server and look at the page if it has browser access.
- **Ask it to verify contrast.** The README lists the exact light-mode text tokens and the darkening map; ask for a check that no pale hue is used as body text in light mode.
- **Ask for the three.js background last.** It's self-contained (README → "3D constellation"), and easy to defer behind a feature flag — the Settings screen already has the toggle.
- **Keep the README in the repo.** It's the source of truth for anyone touching the UI later, not just for the first implementation pass.

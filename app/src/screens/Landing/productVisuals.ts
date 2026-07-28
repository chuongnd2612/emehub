// Per-product visuals for the landing product cards.
//
// The prototype hard-codes each agent's gradient / wash / glow as hexes
// (`#8b5cf6 → #6366f1`, `rgba(139,92,246,.16)`, …). A hex in a `.tsx` is a bug
// (CLAUDE.md › Design › Rules), so every value below is DERIVED from the agent
// tokens `--qagent` / `--dagent` with `color-mix`, which keeps the light-mode
// darkened counterparts working for free.
//
//   tile  — 135deg gradient on the glyph tile + the product's coloured glow
//   wash  — the radial cursor-follow highlight, driven by `--gx` / `--gy`
//           (set by `useCardTilt`)
//   text  — the mono sub-line under the product name
//   cta   — the live product's gradient CTA chip

import type { AgentKey } from "@/data";

export interface ProductVisual {
  tile: string;
  wash: string;
  text: string;
  cta: string;
}

export const PRODUCT_VISUALS: Record<AgentKey, ProductVisual> = {
  q: {
    tile: "bg-[linear-gradient(135deg,var(--qagent),color-mix(in_srgb,var(--qagent)_62%,black))] shadow-[0_12px_30px_-8px_color-mix(in_srgb,var(--qagent)_60%,transparent)]",
    wash: "bg-[radial-gradient(420px_circle_at_var(--gx,50%)_var(--gy,0%),color-mix(in_srgb,var(--qagent)_16%,transparent),transparent_72%)]",
    text: "text-qagent",
    cta: "bg-[linear-gradient(135deg,var(--qagent),color-mix(in_srgb,var(--qagent)_62%,black))] shadow-[0_8px_20px_-6px_color-mix(in_srgb,var(--qagent)_60%,transparent)]",
  },
  d: {
    tile: "bg-[linear-gradient(135deg,var(--dagent),color-mix(in_srgb,var(--dagent)_58%,black))] shadow-[0_12px_30px_-8px_color-mix(in_srgb,var(--dagent)_50%,transparent)]",
    wash: "bg-[radial-gradient(420px_circle_at_var(--gx,50%)_var(--gy,0%),color-mix(in_srgb,var(--dagent)_14%,transparent),transparent_72%)]",
    text: "text-dagent",
    cta: "bg-[linear-gradient(135deg,var(--dagent),color-mix(in_srgb,var(--dagent)_58%,black))] shadow-[0_8px_20px_-6px_color-mix(in_srgb,var(--dagent)_50%,transparent)]",
  },
};

/** The glyph inside the product tile — Handoff › Landing › product cards. */
export const PRODUCT_ICON: Record<AgentKey, "spark" | "code"> = {
  q: "spark",
  d: "code",
};

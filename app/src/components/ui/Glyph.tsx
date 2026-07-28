// Handoff › radius "glyph tile 7–14" — the rounded square that fronts a
// product, provider, project or section. Fills come from three sources:
//   • `fill="accent"`  → the --pg accent gradient (product lockup, avatars)
//   • `fill="<provider>"` → the provider brand colour (Azure/Jira/GitHub/Claude)
//   • `gradient="…"`   → a per-project CSS gradient from the data layer
//
// A per-project gradient is data, not a design decision, so it arrives as a
// prop and is applied via `style` — the computed-value exemption.

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { ClaudeMark } from "./Icon";

export type GlyphFill =
  | "accent"
  | "azure"
  | "jira"
  | "github"
  | "claude"
  | "qagent"
  | "dagent"
  | "neutral";

export interface GlyphProps {
  /** Tile edge length in px. 26 / 34 / 36 / 38 / 44 / 46 across the screens. */
  size?: number;
  fill?: GlyphFill;
  /** A CSS gradient from the data layer (project tiles). Overrides `fill`. */
  gradient?: string;
  /** Short text content — initials or a provider letter. */
  label?: string;
  /** An `<Icon />`. Takes precedence over `label`. */
  icon?: ReactNode;
  /** Renders the filled Claude star. Implies `fill="claude"` styling. */
  claude?: boolean;
  /** Adds the accent glow used by the product lockup. */
  glow?: boolean;
  className?: string;
}

const FILL: Record<GlyphFill, string> = {
  accent: "bg-accent-grad text-white",
  azure: "bg-azure text-white",
  jira: "bg-jira text-white",
  github: "bg-github text-github-glyph",
  claude: "bg-claude-tint text-claude",
  qagent: "bg-qagent-tint text-qagent",
  dagent: "bg-dagent-tint text-dagent",
  neutral: "bg-bd3 border border-bd2 text-txt4",
};

export function Glyph({
  size = 36,
  fill = "accent",
  gradient,
  label,
  icon,
  claude = false,
  glow = false,
  className,
}: GlyphProps) {
  // Radius follows the handoff's 7–14 glyph range, scaled with the tile.
  const radius = Math.round(Math.min(14, Math.max(7, size * 0.31)));
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center font-extrabold",
        gradient ? "text-white" : FILL[claude ? "claude" : fill],
        glow && "shadow-primary",
        className,
      )}
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        fontSize: Math.round(size * 0.36),
        ...(gradient ? { background: gradient } : null),
      }}
    >
      {claude ? <ClaudeMark size={Math.round(size * 0.5)} /> : (icon ?? label)}
    </span>
  );
}

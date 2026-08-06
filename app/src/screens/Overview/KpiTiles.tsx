// Handoff § 2. Overview — KPI tiles.
//
// Prototype: label 10px/700/.1em + a delta chip, value 31px/900/-.04em with a
// trailing unit, and an 8-bar 30px sparkline. Hover raises the tile 3px and
// lifts the border to --bd2.
//
// **The delta chip and the sparkline are not rendered.** Both need history the
// hub does not keep, so the only way to draw them was to invent the numbers —
// which is what the fixture did. Label / value / unit are real counts; see
// `data/overview.ts`. They come back with a real time series and not before.
//
// The tile count is not fixed at four either: `MEMBERS` needs `GET /auth/users`
// and so is absent for a member. The grid is sized to what actually arrived
// rather than left with a hole in it.

import { GlassCard } from "@/components/ui";
import type { Kpi } from "@/data";

/** Tailwind needs literal class names, so the column counts are enumerated. */
const COLUMNS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
};

export function KpiTiles({ kpis }: { kpis: Kpi[] }) {
  if (kpis.length === 0) return null;

  return (
    <div
      className={`grid gap-[14px] ${COLUMNS[Math.min(kpis.length, 4)] ?? "grid-cols-4"}`}
    >
      {kpis.map((k) => (
        <GlassCard
          key={k.label}
          className="flex flex-col gap-3 p-[18px] transition-[transform,border-color] duration-200 hover:-translate-y-[3px] hover:border-bd2"
        >
          <span className="text-[10px] font-bold tracking-[.1em] text-label">
            {k.label}
          </span>

          <div className="flex items-end gap-[10px]">
            <span className="text-[31px] leading-none font-black tracking-[-.04em] text-txt">
              {k.value}
            </span>
            <span className="pb-1 text-[11.5px] text-faint">{k.unit}</span>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}

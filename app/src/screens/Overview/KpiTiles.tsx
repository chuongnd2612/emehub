// Handoff § 2. Overview — 4-up KPI tiles.
//
// Prototype: label 10px/700/.1em + delta chip, value 31px/900/-.04em with a
// trailing unit, and an 8-bar 30px sparkline. Hover raises the tile 3px and
// lifts the border to --bd2.

import { GlassCard, Pill } from "@/components/ui";
import type { Kpi } from "@/data";

export function KpiTiles({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className="grid grid-cols-4 gap-[14px]">
      {kpis.map((k) => (
        <GlassCard
          key={k.label}
          className="flex flex-col gap-3 p-[18px] transition-[transform,border-color] duration-200 hover:-translate-y-[3px] hover:border-bd2"
        >
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold tracking-[.1em] text-label">
              {k.label}
            </span>
            <Pill tone={k.direction === "up" ? "ok" : "danger"} size="sm" mono>
              {k.delta}
            </Pill>
          </div>

          <div className="flex items-end gap-[10px]">
            <span className="text-[31px] leading-none font-black tracking-[-.04em] text-txt">
              {k.value}
            </span>
            <span className="pb-1 text-[11.5px] text-faint">{k.unit}</span>
          </div>

          <div className="flex h-[30px] items-end gap-1">
            {k.bars.map((b, i) => (
              <span
                key={i}
                // Computed value — the bar's height is data (Handoff: inline
                // style only for genuinely computed values).
                style={{ height: `${b}%` }}
                className={`flex-1 origin-bottom animate-bar-grow rounded-[3px] ${
                  i === k.bars.length - 1 ? "bg-accent-grad" : "bg-pb"
                }`}
              />
            ))}
          </div>
        </GlassCard>
      ))}
    </div>
  );
}

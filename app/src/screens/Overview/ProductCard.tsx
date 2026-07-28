// Handoff § 2. Overview — 2-up product cards, the *app variant*: the landing
// card plus a `Launch` / `Preview` button.
//
// Layout from the prototype: perspective:1200px wrapper → tilted card
// (radius 20, glass, gap 14) → header row (26px glyph tile, name 19px/900,
// Live|Placeholder pill, role, CTA) → 3-up mono stat boxes.

import { Glyph, Icon, Pill } from "@/components/ui";
import type { AgentKey, Product } from "@/data";
import { useCardTilt } from "@/hooks/useTilt";

/** The cursor-follow wash. Uses --gx/--gy, which useCardTilt sets on the card. */
const WASH: Record<AgentKey, string> = {
  q: "bg-[radial-gradient(380px_circle_at_var(--gx,50%)_var(--gy,0%),var(--qagentTint),transparent_70%)]",
  d: "bg-[radial-gradient(380px_circle_at_var(--gx,50%)_var(--gy,0%),var(--dagentTint),transparent_70%)]",
};

const ACCENT_TEXT: Record<AgentKey, string> = {
  q: "text-qagent",
  d: "text-dagent",
};

export function ProductCard({ product }: { product: Product }) {
  const tilt = useCardTilt<HTMLDivElement>();

  return (
    <div className="[perspective:1200px]">
      <div
        ref={tilt.ref}
        onMouseMove={tilt.onMouseMove}
        onMouseLeave={tilt.onMouseLeave}
        data-surface
        className="group relative flex flex-col gap-[14px] overflow-hidden rounded-[20px] border border-bd bg-card p-[18px] backdrop-blur-glass"
      >
        <span
          aria-hidden
          className={`pointer-events-none absolute inset-0 rounded-[20px] opacity-0 transition-opacity duration-300 group-hover:opacity-100 ${WASH[product.key]}`}
        />

        <div className="relative flex items-center gap-[14px]">
          <Glyph
            size={26}
            fill={product.key === "q" ? "qagent" : "dagent"}
            icon={<Icon name={product.key === "q" ? "spark" : "code"} size={14} strokeWidth={2.4} />}
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-[9px]">
              <span className="text-[19px] font-black tracking-[-.025em] text-txt">
                {product.name}
              </span>
              <Pill tone={product.live ? "ok" : "neutral"} size="sm">
                {product.live ? "Live" : "Placeholder"}
              </Pill>
            </div>
            <div className="mt-[3px] text-[12px] text-muted">{product.role}</div>
          </div>
          <button
            type="button"
            data-surface
            // NO-OP: neither agent has a destination in the route map yet.
            onClick={() => {}}
            className={`flex shrink-0 cursor-pointer items-center gap-[6px] rounded-[11px] border border-bd2 bg-card2 px-[12px] py-[7px] text-[12px] font-bold transition-[background-color,border-color,transform] duration-200 hover:-translate-y-px hover:border-pb hover:bg-bd ${ACCENT_TEXT[product.key]}`}
          >
            {product.live ? "Launch" : "Preview"}
            <Icon name="arrowRight" size={13} strokeWidth={2.4} />
          </button>
        </div>

        <div className="relative grid grid-cols-3 gap-2">
          {product.stats.map((s) => (
            <div
              key={s.k}
              className="rounded-[13px] border border-bd3 bg-inset px-3 py-[11px]"
            >
              <div className="font-mono text-[17px] font-semibold tracking-[-.02em] text-txt">
                {s.v}
              </div>
              <div className="mt-[3px] text-[9.5px] font-bold tracking-[.09em] text-label">
                {s.k}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

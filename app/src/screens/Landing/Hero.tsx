// Handoff § 1. Landing — hero, as amended by ADR 0012.
//
// Two columns: content left, the WebGL brandmark orb right. The original
// centred hero left the whole right half of the canvas empty; the orb is the
// visual anchor that fills it.
//
// Below ~1024 px the grid collapses to one column and the orb drops away — it
// is decoration, and a phone should not pay for a second WebGL context. The
// left column is the entire message on its own.

import { useNavigate } from "react-router-dom";

import { LogoOrb } from "@/components/orb";
import { Button, Icon } from "@/components/ui";
import { useMediaQuery } from "@/hooks/useMediaQuery";

/** Matches Tailwind's `lg` — the width at which the hero becomes two columns. */
const ORB_BREAKPOINT = "(min-width: 1024px)";

export function Hero() {
  const navigate = useNavigate();
  // Not `hidden lg:block`: a display:none subtree still mounts, and the orb
  // would spend a WebGL context nobody can see.
  const showOrb = useMediaQuery(ORB_BREAKPOINT);

  return (
    <section className="mx-auto grid w-full max-w-[1400px] animate-fade-in-up grid-cols-1 items-center gap-8 px-11 pt-[70px] pb-11 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
      <div className="text-center lg:text-left">
        <div className="mb-7 inline-flex items-center gap-[9px] rounded-pill border border-bd2 bg-card3 px-[15px] py-1.5 text-[12px] font-semibold text-txt3">
          <span className="size-[7px] animate-pulse-dot rounded-full bg-pl shadow-[0_0_10px_var(--pl)]" />
          EMESOFT · AI Operating Center
        </div>

        {/* The line break the centred hero forced is gone: in a column this
            narrow the copy has to reflow with the viewport, so it wraps on its
            own and `balance` keeps the ragged edge even. */}
        <h1 className="text-[clamp(40px,4.6vw,68px)] leading-[1.02] font-black tracking-[-.05em] text-txt [text-wrap:balance]">
          One command center for every{" "}
          <span className="text-silver">AI agent</span> you run
        </h1>

        <p className="mx-auto mt-[26px] max-w-[560px] text-[17px] leading-[1.55] text-muted lg:mx-0 [text-wrap:pretty]">
          Credentials, knowledge, tickets, access and integrations — configured
          once in EmeHub, inherited by every agent your engineering team
          launches.
        </p>

        <div className="mt-9 flex items-center justify-center gap-3 lg:justify-start">
          <Button
            variant="primary"
            size="lg"
            className="h-auto gap-[9px] px-7 py-[15px] shadow-[inset_0_4px_4px_0_var(--glass-hi),0_10px_26px_-8px_var(--pglow)] transition-transform hover:scale-[1.02]"
            trailingIcon={<Icon name="arrowRight" size={16} strokeWidth={2.4} />}
            onClick={() => navigate("/app")}
          >
            Open the hub
          </Button>
          <a
            href="#products"
            className="inline-flex items-center gap-[9px] rounded-button-lg border border-bd2 bg-inset px-[25px] py-[15px] text-[15px] font-semibold text-txt3 transition-colors hover:bg-bd3"
          >
            Meet the agents
          </a>
        </div>
      </div>

      {/* The negative right margin is the "bleeds past the column" in ADR 0012 —
          the sphere runs off the canvas edge rather than sitting politely
          inside a box. */}
      {showOrb && (
        <LogoOrb className="pointer-events-none -mr-[6%] aspect-square w-[106%]" />
      )}
    </section>
  );
}

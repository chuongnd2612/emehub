// Handoff § 1. Landing — header, as amended by ADR 0012.
//
// A floating glass pill rather than the original full-width bar: the old header
// spent an 88 px logo, a divider and a 40 px wordmark on roughly a third of the
// canvas before the hero got a pixel. Sticky at 30 px, `width:fit-content`.
//
// The glass is `.glass-surface` — semi-opaque + 1 px stroke + inner top
// highlight, and deliberately NO `backdrop-filter`: the pill floats over the
// animated constellation, where a backdrop filter both smears and traps child
// z-index in a new stacking context (CLAUDE.md; ADR 0012 § 1).

import { useNavigate } from "react-router-dom";

import { Button, Icon } from "@/components/ui";
import { useLogoTilt } from "@/hooks/useTilt";

export function LandingHeader() {
  const navigate = useNavigate();
  const logo = useLogoTilt();

  return (
    // The sticky element is the wrapper, not the pill: `width:fit-content` on a
    // sticky box would shrink-wrap and stop centring.
    <div className="sticky top-[30px] z-20 flex w-full justify-center px-6">
      <header className="glass-surface flex w-fit max-w-full items-center gap-1.5 rounded-[16px] py-2 pr-2 pl-[18px]">
        <div
          className="[perspective:820px]"
          onMouseMove={logo.onMouseMove}
          onMouseLeave={logo.onMouseLeave}
        >
          <div
            ref={logo.ref}
            className="flex items-center gap-2.5 [transform-style:preserve-3d] will-change-transform"
          >
            {/* The mark alone, not the full lockup: `eme-3d-logo-cut.png` is a
                mark + wordmark + tagline, and at pill scale the wordmark and
                tagline collapse into illegible mush. `eme-mark.png` is that
                file cropped to the infinity mark. */}
            <img
              src="/assets/eme-mark.png"
              alt="EMESOFT"
              className="pointer-events-none block h-[26px] w-auto"
            />
            <span className="text-[17px] font-black tracking-[-.03em] whitespace-nowrap text-txt">
              Eme<span className="text-silver">Hub</span>
            </span>
          </div>
        </div>

        <nav className="ml-4 flex items-center gap-1">
          <a
            href="#products"
            className="rounded-control-lg px-[13px] py-2 text-[13px] font-semibold whitespace-nowrap text-txt3 transition-colors hover:bg-card3 hover:text-txt"
          >
            Products
          </a>
          <a
            href="#platform"
            className="rounded-control-lg px-[13px] py-2 text-[13px] font-semibold whitespace-nowrap text-txt3 transition-colors hover:bg-card3 hover:text-txt"
          >
            Platform
          </a>
        </nav>

        <Button
          variant="primary"
          className="ml-1.5 h-auto rounded-[11px] px-[17px] py-2.5 text-[13px] whitespace-nowrap shadow-[inset_0_4px_4px_0_var(--glass-hi),0_8px_22px_-6px_var(--pglow)] transition-transform hover:scale-[1.02]"
          trailingIcon={<Icon name="arrowRight" size={14} strokeWidth={2.4} />}
          onClick={() => navigate("/app")}
        >
          Enter EmeHub
        </Button>
      </header>
    </div>
  );
}

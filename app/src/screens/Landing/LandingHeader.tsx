// Handoff § 1. Landing — header.
//
// 88px 3D logo (pointer tilt), a 1×56 divider, the `Eme` + silver `Hub`
// wordmark at 40/900/-.04em, then the text links and the primary
// `Enter EmeHub →` button. The handoff's diagonal `metalFlash` sheen was
// removed — it read as an animation glitch, not a shine.

import { useNavigate } from "react-router-dom";

import { Button, Icon } from "@/components/ui";
import { useLogoTilt } from "@/hooks/useTilt";

export function LandingHeader() {
  const navigate = useNavigate();
  const logo = useLogoTilt();

  return (
    <header className="mx-auto flex w-full max-w-[1400px] items-center gap-[18px] px-11 py-[22px]">
      {/* The tilt wrapper carries the perspective; the hook writes the
          transform onto the inner element (computed value → inline style). */}
      <div
        className="[perspective:820px]"
        onMouseMove={logo.onMouseMove}
        onMouseLeave={logo.onMouseLeave}
      >
        <div
          ref={logo.ref}
          className="relative flex items-center gap-5 [filter:drop-shadow(0_16px_26px_var(--shadow))] [transform-style:preserve-3d] will-change-transform"
        >
          <img
            src="/assets/eme-3d-logo-cut.png"
            alt="EMESOFT"
            className="pointer-events-none block h-[88px] w-auto rounded-lg"
          />
          <span className="h-14 w-px bg-bd2" />
          <span className="text-[40px] font-black tracking-[-.04em] text-txt">
            Eme<span className="text-silver">Hub</span>
          </span>
        </div>
      </div>

      <nav className="ml-auto flex items-center gap-1.5">
        <a
          href="#products"
          className="rounded-control-lg px-[15px] py-[9px] text-[13px] font-semibold text-txt3 hover:bg-card3"
        >
          Products
        </a>
        <a
          href="#platform"
          className="rounded-control-lg px-[15px] py-[9px] text-[13px] font-semibold text-txt3 hover:bg-card3"
        >
          Platform
        </a>
        <Button
          variant="primary"
          className="h-auto rounded-button px-[19px] py-[11px] text-[13.5px] shadow-[0_8px_22px_-6px_var(--pglow)] hover:shadow-[0_12px_28px_-8px_var(--pglow)]"
          trailingIcon={<Icon name="arrowRight" size={14} strokeWidth={2.4} />}
          onClick={() => navigate("/app")}
        >
          Enter EmeHub
        </Button>
      </nav>
    </header>
  );
}

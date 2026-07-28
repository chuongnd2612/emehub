// Handoff § 1. Landing — "Final CTA and a compact footer".
//
// The handoff names this band but the prototype's landing view ends at the
// capability grid, so there is no verbatim copy to lift. The two lines below
// are built from the handoff's own sentences (Overview: "configured once in
// EmeHub and inherited by every agent run"), and every button label is copy
// that already exists on this page.

import { useNavigate } from "react-router-dom";

import { Button, Icon } from "@/components/ui";

export function FinalCta() {
  const navigate = useNavigate();

  return (
    <section className="mx-auto w-full max-w-[1400px] animate-fade-in-up px-11 pt-[52px] pb-2.5">
      <div className="glass relative flex flex-col items-center gap-4 overflow-hidden rounded-panel px-11 py-14 text-center shadow-panel">
        <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(620px_circle_at_50%_0%,var(--pt),transparent_70%)]" />
        <h2 className="relative m-0 max-w-[720px] text-[38px] leading-[1.1] font-black tracking-[-.04em] text-txt [text-wrap:balance]">
          Configure once. Every agent inherits it.
        </h2>
        <p className="relative m-0 max-w-[560px] text-[15px] leading-[1.55] text-muted [text-wrap:pretty]">
          Claude credentials, provider connections, project knowledge and
          access — set up in EmeHub, read by every run.
        </p>
        <Button
          variant="primary"
          size="lg"
          className="relative mt-2 h-auto gap-[9px] px-7 py-[15px] shadow-[0_10px_26px_-8px_var(--pglow)] hover:-translate-y-0.5"
          trailingIcon={<Icon name="arrowRight" size={16} strokeWidth={2.4} />}
          onClick={() => navigate("/app")}
        >
          Enter EmeHub
        </Button>
      </div>
    </section>
  );
}

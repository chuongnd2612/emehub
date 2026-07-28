// Handoff § 1. Landing — hero. Centred, `padding:70px 44px 44px`.

import { useNavigate } from "react-router-dom";

import { Button, Icon } from "@/components/ui";

export function Hero() {
  const navigate = useNavigate();

  return (
    <section className="mx-auto w-full max-w-[1400px] animate-fade-in-up px-11 pt-[70px] pb-11 text-center">
      <div className="mb-7 inline-flex items-center gap-[9px] rounded-pill border border-bd2 bg-card3 px-[15px] py-1.5 text-[12px] font-semibold text-txt3">
        <span className="size-[7px] animate-pulse-dot rounded-full bg-pl shadow-[0_0_10px_var(--pl)]" />
        EMESOFT · AI Operating Center
      </div>

      <h1 className="mx-auto max-w-[900px] text-[80px] leading-none font-black tracking-[-.05em] text-txt [text-wrap:balance]">
        One command center
        <br />
        for every <span className="text-silver">AI agent</span> you run
      </h1>

      <p className="mx-auto mt-[26px] max-w-[600px] text-[17px] leading-[1.55] text-muted [text-wrap:pretty]">
        Credentials, knowledge, tickets, access and integrations — configured
        once in EmeHub, inherited by every agent your engineering team launches.
      </p>

      <div className="mt-9 flex items-center justify-center gap-3">
        <Button
          variant="primary"
          size="lg"
          className="h-auto gap-[9px] px-7 py-[15px] shadow-[0_10px_26px_-8px_var(--pglow)] hover:-translate-y-0.5"
          trailingIcon={<Icon name="arrowRight" size={16} strokeWidth={2.4} />}
          onClick={() => navigate("/app")}
        >
          Open the hub
        </Button>
        <a
          href="#products"
          className="inline-flex items-center gap-[9px] rounded-button-lg border border-bd2 bg-inset px-[25px] py-[15px] text-[15px] font-semibold text-txt3 hover:bg-bd3"
        >
          Meet the agents
        </a>
      </div>
    </section>
  );
}

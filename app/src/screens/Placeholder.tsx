// TEMPORARY BRIDGE — wave 1 only.
//
// Every route is registered up front so the wave-2 screen agents can each
// replace exactly one folder under `src/screens/` without any of them editing
// `router.tsx`. Each placeholder renders its screen name and the handoff
// section that specifies it. Delete this file once every screen is real.

import { GlassCard } from "@/components/ui";

export function Placeholder({
  name,
  spec,
}: {
  name: string;
  spec: string;
}) {
  return (
    <GlassCard className="animate-fade-in-up flex flex-col gap-2 p-6">
      <h1 className="m-0 text-[19px] font-black tracking-[-.03em] text-txt">
        {name}
      </h1>
      <p className="m-0 text-[12.5px] leading-[1.6] text-muted">{spec}</p>
    </GlassCard>
  );
}

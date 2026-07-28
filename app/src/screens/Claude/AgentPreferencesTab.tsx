// Handoff › 6. Claude Settings › Agent preferences — "three toggles
// (auto-approve low-risk steps, attach evidence to the provider, stream
// reasoning) + Q‑Agent (`Inherited`) and D‑Agent (`Locked`) override cards".

import type { ReactNode } from "react";
import { GlassCard, Icon, Pill, Toggle } from "@/components/ui";
import { cn } from "@/lib/cn";
import type { ClaudeSettings } from "./state";

export function AgentPreferencesTab({ s }: { s: ClaudeSettings }) {
  return (
    <div className="flex flex-col gap-[14px]">
      <GlassCard radius="panel" className="p-[22px]">
        <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
          Agent behaviour
        </div>
        <div className="mt-2 flex flex-col">
          <PrefRow
            label="Auto-approve low-risk steps"
            description="Agents proceed without asking on read-only and idempotent actions."
            checked={s.prefAuto}
            onChange={s.setPrefAuto}
            divider
          />
          <PrefRow
            label="Attach evidence to the provider"
            description="Screenshots, traces and logs are published back to the work item."
            checked={s.prefEvidence}
            onChange={s.setPrefEvidence}
            divider
          />
          <PrefRow
            label="Stream reasoning to the console"
            description="Verbose output while an agent works. Useful for debugging, noisy day to day."
            checked={s.prefStream}
            onChange={s.setPrefStream}
          />
        </div>
      </GlassCard>

      <div className="grid grid-cols-2 gap-[14px]">
        <OverrideCard
          agent="qagent"
          title="Q‑Agent override"
          meta="Inherits workspace defaults · thinking Medium"
          icon={<Icon name="spark" size={19} strokeWidth={2.2} />}
          state={<Pill tone="ok" size="sm">Inherited</Pill>}
        />
        <OverrideCard
          agent="dagent"
          title="D‑Agent override"
          meta="Placeholder · configuration unlocks at launch"
          icon={<Icon name="code" size={19} strokeWidth={2.3} />}
          state={<Pill tone="dagent" size="sm">Locked</Pill>}
        />
      </div>
    </div>
  );
}

function PrefRow({
  label,
  description,
  checked,
  onChange,
  divider = false,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  divider?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-[14px] py-[15px]",
        divider && "border-b border-bd3",
      )}
    >
      <div className="flex-1">
        <div className="text-[13.5px] font-bold text-txt">{label}</div>
        <div className="mt-[3px] text-[12px] text-muted">{description}</div>
      </div>
      <span className="w-7 text-right text-[11.5px] font-bold text-muted">
        {checked ? "On" : "Off"}
      </span>
      <Toggle checked={checked} onChange={onChange} aria-label={label} />
    </div>
  );
}

function OverrideCard({
  agent,
  title,
  meta,
  icon,
  state,
}: {
  agent: "qagent" | "dagent";
  title: string;
  meta: string;
  icon: ReactNode;
  state: ReactNode;
}) {
  return (
    <div
      data-surface
      className={cn(
        // Derived border colour per agent — see SharedAccounts for why this is
        // not <GlassCard/>.
        "flex items-center gap-[14px] rounded-panel border bg-card p-5 backdrop-blur-glass",
        agent === "qagent" ? "border-qagent/25" : "border-dagent/25",
      )}
    >
      <span
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-button-lg text-white",
          agent === "qagent"
            ? "bg-[linear-gradient(135deg,var(--qagent),var(--brandSoft))]"
            : "bg-[linear-gradient(135deg,var(--dagent),var(--cyanSoft))]",
        )}
      >
        {icon}
      </span>
      <div className="flex-1">
        <div className="text-[14px] font-extrabold text-txt">{title}</div>
        <div className="mt-[3px] text-[12px] text-muted">{meta}</div>
      </div>
      {state}
    </div>
  );
}

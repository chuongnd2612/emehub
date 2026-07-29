// Handoff § 3. Projects › detail › Overview —
//   "4-up KPIs (tickets mirrored, agent runs, pass rate, knowledge confidence
//    with a 6px gradient bar) + 4-up meta row (framework, last indexed, mono
//    knowledge version, page objects)."
//
// AGENT RUNS and PASS RATE are QAgent's run history. The hub stores no runs —
// it owns identity, configuration and knowledge metadata (ADR 0001, ROADMAP
// Phase 4) — so those two tiles show hub-owned configuration counts instead,
// and the notice under the grid says where the run figures actually live.

import { GlassCard, Notice } from "@/components/ui";
import type { Project } from "@/data";
import { confidenceToneClass } from "./shared";

function Kpi({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <GlassCard className="p-[18px]">
      <div className="text-[9.5px] font-bold tracking-[.11em] text-label">
        {label}
      </div>
      {children}
    </GlassCard>
  );
}

function KpiValue({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  return (
    <div
      className={`mt-[7px] text-[28px] font-black tracking-[-.04em] ${className ?? ""}`}
    >
      {value}
    </div>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-bd3 bg-inset px-[17px] py-[15px]">
      <div className="text-[9.5px] font-bold tracking-[.1em] text-label">
        {label}
      </div>
      {children}
    </div>
  );
}

export function OverviewTab({ project }: { project: Project }) {
  const knowledge = project.knowledge;
  const config = project.config;

  return (
    <div className="flex flex-col gap-[14px]">
      <div className="grid grid-cols-4 gap-[14px]">
        <Kpi label="WORK ITEMS MIRRORED">
          <KpiValue value={String(project.tickets)} />
        </Kpi>
        <Kpi label="REPOSITORIES">
          <KpiValue value={String(config?.repos.length ?? 0)} />
        </Kpi>
        <Kpi label="TEST ACCOUNTS">
          <KpiValue value={String(config?.testAccounts.length ?? 0)} />
        </Kpi>
        <Kpi label="KNOWLEDGE CONFIDENCE">
          <div className="mt-[7px] flex items-baseline gap-[6px]">
            <span
              className={`text-[28px] font-black tracking-[-.04em] ${
                knowledge
                  ? confidenceToneClass(knowledge.confidence)
                  : "text-faint"
              }`}
            >
              {knowledge ? knowledge.confidence : "—"}
            </span>
            {knowledge && (
              <span className="text-[13px] font-bold text-label">%</span>
            )}
          </div>
          <div className="mt-[11px] h-[6px] overflow-hidden rounded-[6px] bg-bd2">
            {/* Width is a computed value — the inline-style exemption. */}
            <div
              className="h-full rounded-[6px] bg-[linear-gradient(90deg,var(--p),var(--pl))]"
              style={{ width: `${knowledge?.confidence ?? 0}%` }}
            />
          </div>
        </Kpi>
      </div>

      <div className="grid grid-cols-4 gap-[14px]">
        <Meta label="FRAMEWORK">
          <div className="mt-[5px] text-[13px] font-bold text-txt2">
            {knowledge?.framework || "not detected"}
          </div>
        </Meta>
        <Meta label="LAST INDEXED">
          <div className="mt-[5px] text-[13px] font-bold text-txt2">
            {knowledge?.lastIndexedLabel ?? "never"}
          </div>
        </Meta>
        <Meta label="KNOWLEDGE VERSION">
          <div className="mt-[5px] font-mono text-[13px] font-semibold text-ps-text">
            {knowledge?.version ?? "—"}
          </div>
        </Meta>
        <Meta label="PAGE OBJECTS">
          <div className="mt-[5px] text-[13px] font-bold text-txt2">
            {knowledge ? `${knowledge.body.pageObjects} reusable` : "—"}
          </div>
        </Meta>
      </div>

      <Notice tone="info">
        Agent run counts and pass rates live with the agent that produced them.
        EmeHub is the source of truth for identity, configuration and knowledge
        metadata — it runs nothing itself.
      </Notice>
    </div>
  );
}

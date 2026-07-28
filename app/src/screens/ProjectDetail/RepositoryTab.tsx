// Handoff § 3. Projects › detail › Repository —
//   "detected stack chips, 'shared utilities the agents reuse' mono rows, 4-up
//    counters (indexed assets, page objects, fixtures, default branch)."

import { GlassCard, Icon } from "@/components/ui";
import type { Project } from "@/data";

function Counter({
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

export function RepositoryTab({ project }: { project: Project }) {
  const { stack, utils, assets, pageObjects, fixtures } = project.repository;

  return (
    <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] items-start gap-[14px]">
      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="text-[15px] font-extrabold tracking-[-.01em]">
          Detected stack
        </div>
        <div className="mt-[14px] flex flex-wrap gap-2">
          {stack.map((s) => (
            <span
              key={s}
              className="rounded-pill border border-bd2 bg-card3 px-3 py-[6px] text-[12px] font-semibold text-txt3"
            >
              {s}
            </span>
          ))}
        </div>

        <div className="my-5 h-px bg-bd3" />

        <div className="text-[9.5px] font-bold tracking-[.11em] text-label">
          SHARED UTILITIES THE AGENTS REUSE
        </div>
        <div className="mt-3 flex flex-col gap-2">
          {utils.map((u) => (
            <div
              key={u}
              className="flex items-center gap-[10px] rounded-button border border-bd3 bg-inset px-[14px] py-[11px]"
            >
              <span className="flex shrink-0 text-ps-text">
                <Icon name="code" size={14} strokeWidth={2.2} />
              </span>
              <span className="font-mono text-[12px] text-txt2">{u}</span>
            </div>
          ))}
        </div>
      </GlassCard>

      <div className="grid grid-cols-2 gap-[14px]">
        <Counter label="INDEXED ASSETS">
          <div className="mt-[7px] text-[26px] font-black tracking-[-.04em]">
            {assets}
          </div>
        </Counter>
        <Counter label="PAGE OBJECTS">
          <div className="mt-[7px] text-[26px] font-black tracking-[-.04em]">
            {pageObjects}
          </div>
        </Counter>
        <Counter label="FIXTURES">
          <div className="mt-[7px] text-[26px] font-black tracking-[-.04em]">
            {fixtures}
          </div>
        </Counter>
        <Counter label="DEFAULT BRANCH">
          <div className="mt-[11px] font-mono text-[13px] font-semibold text-txt2">
            {project.branch}
          </div>
        </Counter>
      </div>
    </div>
  );
}

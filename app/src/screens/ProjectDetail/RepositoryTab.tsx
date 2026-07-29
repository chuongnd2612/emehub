// Handoff § 3. Projects › detail › Repository —
//   "detected stack chips, 'shared utilities the agents reuse' mono rows, 4-up
//    counters (indexed assets, page objects, fixtures, default branch)."
//
// Two sources, and they are different things:
//   • the CONFIGURED repositories are now EDITABLE here (`RepositoryEditor.tsx`
//     — discover from the bound Repository Provider connection, or add a
//     clone URL manually, matching Q-Agent's `ReposManager.tsx`). The handoff
//     only drew this as a read-only list; there was previously no way to add
//     a repository anywhere in the product.
//   • the detected stack, utilities and counters come from the knowledge blob
//     an agent reported. Without a knowledge base there is nothing detected,
//     and the counters say so rather than showing four zeroes as if they were
//     measurements.

import { GlassCard, Icon, Notice } from "@/components/ui";
import type { Project } from "@/data";
import { RepositoryEditor } from "./RepositoryEditor";

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

export function RepositoryTab({
  project,
  onReload,
  onOpenSettings,
}: {
  project: Project;
  onReload: () => void;
  /** Where "bind a connection first" sends the user. */
  onOpenSettings: () => void;
}) {
  const body = project.knowledge?.body ?? null;

  return (
    <div className="flex flex-col gap-[14px]">
      <RepositoryEditor
        project={project}
        onReload={onReload}
        onOpenSettings={onOpenSettings}
      />

      {!body ? (
        <Notice tone="info">
          Detected stack, shared utilities and the indexed counters come from a
          knowledge base. This project does not have one yet.
        </Notice>
      ) : (
        <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] items-start gap-[14px]">
          <GlassCard className="rounded-[20px] p-[22px]">
            <div className="text-[15px] font-extrabold tracking-[-.01em]">
              Detected stack
            </div>
            {body.stack.length === 0 ? (
              <div className="mt-3 text-[12.5px] text-muted">
                The agent reported no stack for this repository.
              </div>
            ) : (
              <div className="mt-[14px] flex flex-wrap gap-2">
                {body.stack.map((s) => (
                  <span
                    key={s}
                    className="rounded-pill border border-bd2 bg-card3 px-3 py-[6px] text-[12px] font-semibold text-txt3"
                  >
                    {s}
                  </span>
                ))}
              </div>
            )}

            <div className="my-5 h-px bg-bd3" />

            <div className="text-[9.5px] font-bold tracking-[.11em] text-label">
              SHARED UTILITIES THE AGENTS REUSE
            </div>
            {body.utilities.length === 0 ? (
              <div className="mt-3 text-[12.5px] text-muted">
                None reported.
              </div>
            ) : (
              <div className="mt-3 flex flex-col gap-2">
                {body.utilities.map((u) => (
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
            )}
          </GlassCard>

          <div className="grid grid-cols-2 gap-[14px]">
            <Counter label="INDEXED ASSETS">
              <div className="mt-[7px] text-[26px] font-black tracking-[-.04em]">
                {body.assets}
              </div>
            </Counter>
            <Counter label="PAGE OBJECTS">
              <div className="mt-[7px] text-[26px] font-black tracking-[-.04em]">
                {body.pageObjects}
              </div>
            </Counter>
            <Counter label="FIXTURES">
              <div className="mt-[7px] text-[26px] font-black tracking-[-.04em]">
                {body.fixtures}
              </div>
            </Counter>
            <Counter label="DEFAULT BRANCH">
              <div className="mt-[11px] font-mono text-[13px] font-semibold text-txt2">
                {project.branch || "—"}
              </div>
            </Counter>
          </div>
        </div>
      )}
    </div>
  );
}

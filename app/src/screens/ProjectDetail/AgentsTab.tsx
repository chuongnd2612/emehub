// Handoff § 3. Projects › detail › Agents —
//   "agents wired to this project + a note pointing at Claude Settings ›
//    Agent preferences."
//
// Nothing in the hub maps an agent to a project yet — `Project.agents` is
// always empty for a live row — so the list is honest about being empty and the
// notice says how an agent actually reaches this project today: by reading the
// registry through the integration contract with its own token.

import { GlassCard, Icon, Notice, Pill } from "@/components/ui";
import type { Project } from "@/data";
import { AGENT_LABEL, agentTone } from "./shared";

export function AgentsTab({ project }: { project: Project }) {
  return (
    <div className="flex flex-col gap-[14px]">
      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="text-[15px] font-extrabold tracking-[-.01em]">
          Agents wired to this project
        </div>
        <div className="mt-1 text-[12.5px] text-muted">
          Each agent inherits the credential, model policy and knowledge base
          configured here.
        </div>
        <div className="mt-4 flex flex-wrap gap-[9px]">
          {project.agents.map((a) => (
            <Pill key={a} tone={agentTone(a)}>
              {AGENT_LABEL[a]}
            </Pill>
          ))}
          {project.agents.length === 0 && (
            <span className="rounded-pill bg-card3 px-[11px] py-[5px] text-[11px] font-semibold text-faint">
              No agent wired
            </span>
          )}
        </div>
      </GlassCard>

      <Notice tone="info">
        EmeHub does not assign agents to projects yet. Any agent holding a token
        for this workspace already reads{" "}
        <b className="font-bold">{project.id}</b> — its configuration, its
        repositories and its knowledge — through the integration contract.
      </Notice>

      <div className="flex items-center gap-[14px] rounded-card border border-bd3 bg-inset px-5 py-[18px]">
        <span className="flex shrink-0 text-ps-text">
          <Icon name="alert" size={17} strokeWidth={2.2} />
        </span>
        <span className="text-[12.5px] text-pretty text-txt3">
          Agent-level overrides live in{" "}
          <b className="font-bold text-txt">
            Claude Settings › Agent preferences
          </b>
          . Anything left untouched follows the workspace default.
        </span>
      </div>
    </div>
  );
}

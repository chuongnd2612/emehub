// Handoff § 3. Projects › detail › Settings —
//   "Project knowledge summary row (status · version · last indexed) with
//    `Open knowledge base →`, then three toggles: Re-index on every merge to
//    <branch>, Publish evidence back to <provider>, Block runs on a stale
//    index; then a 3-up read-only meta grid (provider, repository, knowledge
//    scope)."
//
// **The three toggles are gone** (#191). `ProjectConfigIn` has no field for a
// re-index-on-merge, publish-evidence or block-on-stale policy, so they were
// local `useState` that reset on every navigation and changed nothing — a
// notice underneath even admitted it. A switch that stores nothing is worse
// than an absent one: it reads as configuration. They come back with the
// fields that would store them.
//
// Everything BELOW that card is not in the handoff at all — it is the
// functional core of Q-Agent's `ProjectSettingsForm.tsx`, ported because it is
// what actually configures a project (connection bindings, base URL, test
// accounts, environments) and EmeHub had no equivalent. See
// `ProjectConfigForm.tsx` for what was and wasn't carried over, and why.

import { Button, GlassCard, Icon } from "@/components/ui";
import type { Project } from "@/data";
import { DangerZone } from "./DangerZone";
import { ProjectConfigForm } from "./ProjectConfigForm";
import type { KnowledgeStatusLabel } from "./shared";

function MetaCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-bd3 bg-inset p-[18px]">
      <div className="text-[9.5px] font-bold tracking-[.11em] text-label">
        {label}
      </div>
      {children}
    </div>
  );
}

export function SettingsTab({
  project,
  knowledgeStatusLabel,
  onOpenKnowledge,
  onReload,
}: {
  project: Project;
  knowledgeStatusLabel: KnowledgeStatusLabel;
  onOpenKnowledge: () => void;
  /** Re-reads the project after `ProjectConfigForm` saves. */
  onReload: () => void;
}) {
  const knowledge = project.knowledge;

  return (
    <div className="flex flex-col gap-[14px]">
      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="flex items-center gap-[14px]">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-button border border-pb bg-pt text-ps-text">
            <Icon name="book" size={19} strokeWidth={2.1} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-extrabold tracking-[-.01em]">
              Project knowledge
            </div>
            <div className="mt-[3px] text-[12.5px] text-muted">
              {knowledgeStatusLabel} · {knowledge?.version ?? "no version"} ·
              last indexed {knowledge?.lastIndexedLabel ?? "never"}
            </div>
          </div>
          <Button
            className="h-auto rounded-control-lg px-4 py-[10px]"
            trailingIcon={<Icon name="arrowRight" size={14} strokeWidth={2.4} />}
            onClick={onOpenKnowledge}
          >
            Open knowledge base
          </Button>
        </div>
      </GlassCard>

      <div className="grid grid-cols-3 gap-[14px]">
        <MetaCard label="PROVIDER">
          <div className="mt-[6px] text-[13px] font-bold text-txt2">
            {project.providerName}
          </div>
        </MetaCard>
        <MetaCard label="REPOSITORY">
          <div className="mt-[6px] truncate font-mono text-[12px] text-txt2">
            {project.repo || "none connected"}
          </div>
        </MetaCard>
        <MetaCard label="KNOWLEDGE SCOPE">
          <div className="mt-[6px] text-[13px] font-bold text-txt2">
            {project.shared ? "Shared workspace" : "This project only"}
          </div>
        </MetaCard>
      </div>

      <ProjectConfigForm project={project} onSaved={onReload} />

      <DangerZone project={project} />
    </div>
  );
}

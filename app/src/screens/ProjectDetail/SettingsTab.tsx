// Handoff § 3. Projects › detail › Settings —
//   "Project knowledge summary row (status · version · last indexed) with
//    `Open knowledge base →`, then three toggles: Re-index on every merge to
//    <branch>, Publish evidence back to <provider>, Block runs on a stale
//    index; then a 3-up read-only meta grid (provider, repository, knowledge
//    scope)."
//
// The three toggles above have no storage: `ProjectConfigIn` has no field for
// a re-index-on-merge or block-on-stale policy. They stay local UI state.
//
// Everything BELOW that card is not in the handoff at all — it is the
// functional core of Q-Agent's `ProjectSettingsForm.tsx`, ported because it is
// what actually configures a project (connection bindings, base URL, test
// accounts, environments) and EmeHub had no equivalent. See
// `ProjectConfigForm.tsx` for what was and wasn't carried over, and why.

import { useState } from "react";

import { Button, GlassCard, Icon, Notice, Toggle } from "@/components/ui";
import type { Project } from "@/data";
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
  // Handoff › State Management › Projects: pjAutoIndex, pjEvidence,
  // pjBlockUnindexed. UI-only, scoped to this screen — see the header comment.
  const [autoIndex, setAutoIndex] = useState(true);
  const [evidence, setEvidence] = useState(true);
  const [blockStale, setBlockStale] = useState(false);

  const knowledge = project.knowledge;
  const branch = project.branch || "the default branch";

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

        <div className="mt-2 flex flex-col gap-[2px]">
          <div className="border-t border-bd3 py-[15px]">
            <Toggle
              checked={autoIndex}
              onChange={setAutoIndex}
              label={`Re-index on every merge to ${branch}`}
              description="Keeps the knowledge base in step with the default branch without manual runs."
            />
          </div>
          <div className="border-t border-bd3 py-[15px]">
            <Toggle
              checked={evidence}
              onChange={setEvidence}
              label={`Publish evidence back to ${project.providerName}`}
              description="Screenshots, traces and generated cases are attached to the originating work item."
            />
          </div>
          <div className="border-t border-bd3 py-[15px]">
            <Toggle
              checked={blockStale}
              onChange={setBlockStale}
              label="Block runs on a stale index"
              description="Agents refuse to start when the knowledge base is older than the current head."
            />
          </div>
        </div>

        <Notice tone="warn" className="mt-3">
          These three policies are not stored yet — the hub has no field for
          them. The project configuration below (connections, base URL, test
          accounts, environments) is real and saves to the hub.
        </Notice>
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
    </div>
  );
}

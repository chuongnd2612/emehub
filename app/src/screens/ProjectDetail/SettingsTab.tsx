// Handoff § 3. Projects › detail › Settings —
//   "Project knowledge summary row (status · version · last indexed) with
//    `Open knowledge base →`, then three toggles: Re-index on every merge to
//    <branch>, Publish evidence back to <provider>, Block runs on a stale
//    index; then a 3-up read-only meta grid (provider, repository, knowledge
//    scope)."

import { useState } from "react";

import { Button, GlassCard, Icon, Toggle } from "@/components/ui";
import type { Project } from "@/data";
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
}: {
  project: Project;
  knowledgeStatusLabel: KnowledgeStatusLabel;
  onOpenKnowledge: () => void;
}) {
  // Handoff › State Management › Projects: pjAutoIndex, pjEvidence,
  // pjBlockUnindexed. UI-only, scoped to this screen.
  const [autoIndex, setAutoIndex] = useState(true);
  const [evidence, setEvidence] = useState(true);
  const [blockStale, setBlockStale] = useState(false);

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
              {knowledgeStatusLabel} · {project.knowledgeVersion} · last indexed{" "}
              {project.lastIndexed}
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
              label={`Re-index on every merge to ${project.branch}`}
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
      </GlassCard>

      <div className="grid grid-cols-3 gap-[14px]">
        <MetaCard label="PROVIDER">
          <div className="mt-[6px] text-[13px] font-bold text-txt2">
            {project.providerName}
          </div>
        </MetaCard>
        <MetaCard label="REPOSITORY">
          <div className="mt-[6px] truncate font-mono text-[12px] text-txt2">
            {project.repo}
          </div>
        </MetaCard>
        <MetaCard label="KNOWLEDGE SCOPE">
          <div className="mt-[6px] text-[13px] font-bold text-txt2">
            This project only
          </div>
        </MetaCard>
      </div>
    </div>
  );
}

// Handoff § 2. Overview — the right column: the **integration strip** and the
// **top-3 projects** summary rows.

import { useNavigate } from "react-router-dom";

import { GlassCard, Glyph, StatusPill, type StatusName } from "@/components/ui";
import { PROVIDERS, type AgentKey, type Integration, type Project } from "@/data";

const AGENT_DOT: Record<AgentKey, string> = {
  q: "bg-qagent",
  d: "bg-dagent",
};

function PanelHeading({
  title,
  action,
  onAction,
}: {
  title: string;
  action: string;
  onAction: () => void;
}) {
  return (
    <div className="mb-[14px] flex items-center gap-[10px]">
      <span className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
        {title}
      </span>
      <button
        type="button"
        data-surface
        onClick={onAction}
        className="ml-auto cursor-pointer border-none bg-transparent p-0 text-[11.5px] font-semibold text-ps-text"
      >
        {action}
      </button>
    </div>
  );
}

export function IntegrationStrip({
  integrations,
}: {
  integrations: Integration[];
}) {
  const navigate = useNavigate();
  return (
    <GlassCard radius="panel" className="p-5">
      <PanelHeading
        title="Connected integrations"
        action="Manage"
        onAction={() => navigate("/app/integrations")}
      />
      <div className="flex flex-col gap-[9px]">
        {integrations.map((i) => (
          <div
            key={i.id}
            data-surface
            className="flex items-center gap-[11px] rounded-[13px] border border-bd3 bg-inset px-3 py-[11px] hover:bg-bd3"
          >
            <Glyph
              size={28}
              fill={PROVIDERS[i.id].color}
              label={PROVIDERS[i.id].glyph}
            />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-bold text-txt2">
                {i.name}
              </div>
              <div className="mt-[2px] truncate text-[10.5px] text-faint">
                {i.meta}
              </div>
            </div>
            <StatusPill status={i.state as StatusName} size="sm" />
          </div>
        ))}
      </div>
    </GlassCard>
  );
}

export function TopProjects({ projects }: { projects: Project[] }) {
  const navigate = useNavigate();
  const top = projects.slice(0, 3);

  return (
    <GlassCard radius="panel" className="p-5">
      <PanelHeading
        title="Active projects"
        action={`All ${projects.length}`}
        onAction={() => navigate("/app/projects")}
      />
      <div className="flex flex-col gap-[9px]">
        {top.map((p) => (
          <button
            key={p.id}
            type="button"
            data-surface
            onClick={() => navigate(`/app/projects/${encodeURIComponent(p.guid || p.id)}`)}
            className="flex w-full cursor-pointer items-center gap-[11px] rounded-[13px] border border-bd3 bg-inset px-3 py-[11px] text-left hover:bg-bd3"
          >
            <Glyph size={30} gradient={p.gradient} label={p.initials} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12.5px] font-bold text-txt2">
                {p.name}
              </span>
              <span className="mt-[2px] block truncate font-mono text-[10px] text-label">
                {p.repo}
              </span>
            </span>
            <span className="flex shrink-0 gap-1">
              {p.agents.map((a) => (
                <span
                  key={a}
                  className={`size-[6px] rounded-full ${AGENT_DOT[a]}`}
                />
              ))}
            </span>
          </button>
        ))}
      </div>
    </GlassCard>
  );
}

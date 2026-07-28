// Handoff § 3. Projects & Repositories — LIST STATE.
//
//   "3-up card grid (gap 14) + a dashed 'Connect a repository' tile:
//    38px initials tile in the project gradient, name 15px/800, mono repo path
//    10.5px var(--faint); 3-up mini stats (cases / coverage / branch) in
//    var(--inset) boxes with mono values; agent tag pills, provider name
//    right-aligned, `Configure` ghost button + 'updated' timestamp.
//    Card hover: translateY(-3px), border → var(--pb), background → var(--card3)."
//
// `Configure` navigates to /app/projects/:projectId — the URL is the source of
// truth for navigation (CLAUDE.md). ProjectDetail resets the scroll region on
// mount, which is the other half of the handoff's "sets projectId, tab
// overview, resets scroll".

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, GlassCard, Glyph, Icon, Pill } from "@/components/ui";
import { getProjects, type AgentKey, type Project } from "@/data";
import { useUi } from "@/store/ui";

/** Agent display names — Handoff › "Agent tag pills (Q-Agent, D-Agent)". */
const AGENT_LABEL: Record<AgentKey, string> = {
  q: "Q-Agent",
  d: "D-Agent",
};

function MiniStat({
  value,
  label,
  small = false,
}: {
  value: string;
  label: string;
  small?: boolean;
}) {
  return (
    <div className="rounded-control-lg border border-bd3 bg-inset p-[10px]">
      <div
        className={
          small
            ? "pt-[3px] font-mono text-[11px] font-semibold text-txt2"
            : "font-mono text-[14px] font-semibold text-txt2"
        }
      >
        {value}
      </div>
      <div
        className={`text-[9px] font-bold tracking-[.09em] text-label ${
          small ? "mt-[3px]" : "mt-[2px]"
        }`}
      >
        {label}
      </div>
    </div>
  );
}

function ProjectCard({ project }: { project: Project }) {
  const navigate = useNavigate();
  return (
    <GlassCard
      hoverable
      className="flex flex-col gap-[14px] rounded-[20px] p-[18px]"
    >
      <div className="flex items-center gap-3">
        <Glyph size={38} gradient={project.gradient} label={project.initials} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[15px] font-extrabold tracking-[-.015em]">
            {project.name}
          </div>
          <div className="mt-[3px] truncate font-mono text-[10.5px] text-faint">
            {project.repo}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <MiniStat value={String(project.tests)} label="CASES" />
        <MiniStat value={project.coverage} label="COVERAGE" />
        <MiniStat value={project.branch} label="BRANCH" small />
      </div>

      <div className="flex flex-wrap items-center gap-[7px]">
        {project.agents.map((a) => (
          <Pill key={a} tone={a === "q" ? "qagent" : "dagent"} size="sm">
            {AGENT_LABEL[a]}
          </Pill>
        ))}
        {project.agents.length === 0 && (
          <span className="rounded-pill bg-card3 px-2 py-[3px] text-[10px] font-semibold text-faint">
            No agent wired
          </span>
        )}
        <span className="ml-auto text-[10.5px] text-label">
          {project.providerName}
        </span>
      </div>

      <div className="flex items-center gap-[9px] pt-[2px]">
        <Button
          className="flex-1"
          onClick={() => navigate(`/app/projects/${project.id}`)}
        >
          Configure
        </Button>
        <span className="whitespace-nowrap text-[10.5px] text-label">
          {project.updated}
        </span>
      </div>
    </GlassCard>
  );
}

export default function ProjectsScreen() {
  const [projects, setProjects] = useState<Project[]>([]);
  const setModal = useUi((s) => s.setModal);

  useEffect(() => {
    let live = true;
    void getProjects().then((rows) => {
      if (live) setProjects(rows);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="flex animate-fade-in-up flex-col gap-[14px]">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[12.5px] font-semibold text-muted">
          {projects.length} projects · 5 repositories connected · 2 agents wired
        </span>
        <Button
          variant="primary"
          className="ml-auto h-auto rounded-button px-[18px] py-[11px] text-[13px]"
          icon={<Icon name="plus" size={15} strokeWidth={2.6} />}
          onClick={() => setModal("project")}
        >
          New project
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-[14px]">
        {projects.map((p) => (
          <ProjectCard key={p.id} project={p} />
        ))}

        <button
          type="button"
          data-surface
          onClick={() => setModal("project")}
          className="flex min-h-[180px] cursor-pointer flex-col items-center justify-center gap-[10px] rounded-[20px] border border-dashed border-bd2 bg-transparent text-faint transition-[background-color,border-color,color] duration-200 hover:border-pb hover:bg-inset hover:text-ps-text"
        >
          <Icon name="plus" size={22} strokeWidth={2.2} />
          <span className="text-[13px] font-bold">Connect a repository</span>
        </button>
      </div>
    </div>
  );
}

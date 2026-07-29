// Handoff § 3. Projects & Repositories — LIST STATE.
//
//   "3-up card grid (gap 14) + a dashed 'Connect a repository' tile:
//    38px initials tile in the project gradient, name 15px/800, mono repo path
//    10.5px var(--faint); 3-up mini stats in var(--inset) boxes with mono
//    values; agent tag pills, provider name right-aligned, `Configure` ghost
//    button + 'updated' timestamp."
//
// `Configure` navigates to /app/projects/:projectKey — the URL is the source of
// truth for navigation (CLAUDE.md).
//
// ## The three mini stats
//
// The handoff's are CASES / COVERAGE / BRANCH. Cases and coverage are QAgent's
// test-suite figures; the hub stores no runs and no suites (ADR 0001), so they
// are replaced with two facts the hub does own — mirrored work items and
// knowledge confidence — rather than rendered as a plausible-looking number.

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  Button,
  EmptyState,
  ErrorState,
  GlassCard,
  Glyph,
  Icon,
  LoadingState,
  Pill,
} from "@/components/ui";
import { getProjects, type AgentKey, type Project } from "@/data";
import { ApiError } from "@/lib/api";
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
            ? "truncate pt-[3px] font-mono text-[11px] font-semibold text-txt2"
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
  // A list row carries the hub's `summary` and a null `knowledge` object (the
  // list response deliberately holds no config or knowledge). Prefer the full
  // object when present, fall back to the summary scalars, so this card works
  // from either read.
  const indexed =
    (project.knowledge?.status ?? project.knowledgeStatus) === "indexed";
  const confidence =
    project.knowledge?.confidence ?? project.knowledgeConfidence ?? 0;

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
            {project.repo || project.id}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <MiniStat value={String(project.tickets)} label="WORK ITEMS" />
        <MiniStat
          value={indexed ? `${confidence}%` : "—"}
          label="CONFIDENCE"
        />
        <MiniStat value={project.branch || "—"} label="BRANCH" small />
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
          onClick={() =>
            navigate(`/app/projects/${encodeURIComponent(project.id)}`)
          }
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
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const setModal = useUi((s) => s.setModal);
  const modal = useUi((s) => s.modal);

  const load = useCallback(() => {
    let live = true;
    setStatus("loading");
    void getProjects()
      .then((rows) => {
        if (!live) return;
        setProjects(rows);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (!live) return;
        setError(
          err instanceof ApiError ? err.message : "The hub did not respond.",
        );
        setStatus("error");
      });
    return () => {
      live = false;
    };
  }, []);

  // The New project modal is mounted globally, so reload whenever it closes —
  // a project created there appears without a manual refresh.
  useEffect(() => {
    if (modal === "project") return;
    return load();
  }, [modal, load]);

  const newProject = (
    <Button
      variant="primary"
      className="h-auto rounded-button px-[18px] py-[11px] text-[13px]"
      icon={<Icon name="plus" size={15} strokeWidth={2.6} />}
      onClick={() => setModal("project")}
    >
      New project
    </Button>
  );

  // `repoCount` and `knowledgeStatus` come from the hub's list summary;
  // `p.repo`/`p.knowledge` are the detail-read equivalents.
  const repos = projects.reduce(
    (n, p) => n + (p.repoCount ?? (p.repo ? 1 : 0)),
    0,
  );
  const indexed = projects.filter(
    (p) => (p.knowledge?.status ?? p.knowledgeStatus) === "indexed",
  ).length;

  return (
    <div className="flex animate-fade-in-up flex-col gap-[14px]">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[12.5px] font-semibold text-muted">
          {projects.length} project{projects.length === 1 ? "" : "s"} · {repos}{" "}
          repositor{repos === 1 ? "y" : "ies"} connected · {indexed} knowledge
          base{indexed === 1 ? "" : "s"}
        </span>
        <span className="ml-auto">{newProject}</span>
      </div>

      {status === "loading" && <LoadingState label="Loading projects…" />}

      {status === "error" && (
        <GlassCard className="rounded-[20px]">
          <ErrorState
            title="Could not load your projects"
            detail={error}
            onRetry={load}
          />
        </GlassCard>
      )}

      {status === "ready" && projects.length === 0 && (
        <GlassCard className="rounded-[20px]">
          <EmptyState
            icon="folder"
            title="No projects yet"
            body="A project is what every agent inherits — its repositories, environments, test accounts and knowledge base. Register the first one and the rest hangs off it."
            action={newProject}
          />
        </GlassCard>
      )}

      {status === "ready" && projects.length > 0 && (
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
      )}
    </div>
  );
}

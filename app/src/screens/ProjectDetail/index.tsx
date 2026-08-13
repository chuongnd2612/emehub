// Handoff § 3. Projects & Repositories — DETAIL STATE (`/app/projects/:id`).
//
//   "Back link `← All projects`. Header card: 46px provider glyph, name
//    23px/900, agent pills, mono `repo · branch · provider`, knowledge status
//    pill … Tab row: Overview · Project knowledge · Repository · Agents ·
//    Settings."
//
// The active tab lives in the `?tab=` QUERY PARAM — never in Zustand and never
// in the path (CLAUDE.md › "Intra-screen selection goes in query params").
// `:projectId` is the project's GUID (#150), read from the URL via useParams and
// passed straight to the API, which accepts a GUID anywhere it accepts a key. A
// key-shaped param therefore still resolves, so older links keep working.
//
// ## The two header buttons the handoff draws, and why one is gone
//
// `Re-index knowledge` cannot exist here: the hub does not clone repositories
// and does not run `project-bootstrap` — the agent builds on its own host and
// reports the result with `PUT /projects/{key}/repos/{repo}/knowledge`
// (ROADMAP.md Phase 4). A button that toasted "Re-index queued" would be a
// button that does nothing, so it is replaced by `Reload`, which genuinely
// re-reads the registry row, its config and its knowledge metadata — the useful
// action when an agent has reported a build since the page opened. The
// knowledge tab explains who does the building.

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  Button,
  ErrorState,
  GlassCard,
  Glyph,
  Icon,
  LoadingState,
  Pill,
} from "@/components/ui";
import { getProject, type Project } from "@/data";
import { ApiError } from "@/lib/api";

import { AgentsTab } from "./AgentsTab";
import { KnowledgeTab } from "./KnowledgeTab";
import { OverviewTab } from "./OverviewTab";
import { RepositoryTab } from "./RepositoryTab";
import { SettingsTab } from "./SettingsTab";
import {
  AGENT_LABEL,
  PROJECT_TABS,
  PROVIDER_GLYPH,
  UNKNOWN_GLYPH,
  agentTone,
  isProjectTab,
  knowledgeStatus,
  knowledgeStatusTone,
  type ProjectTab,
} from "./shared";

/**
 * Handoff › Interactions › Navigation — "Projects list → detail via Configure
 * (sets projectId, tab overview, RESETS SCROLL)". The scroll region belongs to
 * the app shell, so walk up to the nearest scrollable ancestor rather than
 * reaching into another agent's component.
 */
function useResetScrollOnMount() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let el: HTMLElement | null = ref.current?.parentElement ?? null;
    while (el) {
      const overflowY = getComputedStyle(el).overflowY;
      if (overflowY === "auto" || overflowY === "scroll") {
        el.scrollTop = 0;
        return;
      }
      el = el.parentElement;
    }
    window.scrollTo(0, 0);
  }, []);
  return ref;
}

export default function ProjectDetailScreen() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const rootRef = useResetScrollOnMount();

  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    let live = true;
    setStatus("loading");
    void getProject(projectId)
      .then((p) => {
        if (!live) return;
        setProject(p);
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
  }, [projectId]);

  useEffect(load, [load]);

  const tabParam = searchParams.get("tab");
  const tab: ProjectTab = isProjectTab(tabParam) ? tabParam : "overview";

  const setTab = (next: ProjectTab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  // An unknown :projectId falls back to the list — never guess a project.
  useEffect(() => {
    if (status === "ready" && !project) {
      navigate("/app/projects", { replace: true });
    }
  }, [status, project, navigate]);

  if (status === "loading") {
    return (
      <div ref={rootRef}>
        <LoadingState label="Loading project…" />
      </div>
    );
  }

  if (status === "error") {
    return (
      <div ref={rootRef}>
        <GlassCard className="rounded-[20px]">
          <ErrorState
            title="Could not load this project"
            detail={error}
            onRetry={load}
          />
        </GlassCard>
      </div>
    );
  }

  if (!project) return <div ref={rootRef} />;

  const knowledge = project.knowledge;
  const label = knowledgeStatus(knowledge);
  const provider = project.provider
    ? PROVIDER_GLYPH[project.provider]
    : UNKNOWN_GLYPH;

  const subtitle = [project.repo, project.branch, project.providerName]
    .filter(Boolean)
    .join(" · ");

  return (
    <div ref={rootRef} className="flex animate-fade-in-up flex-col gap-[14px]">
      <Link
        to="/app/projects"
        className="flex items-center gap-2 self-start text-[12.5px] font-semibold text-muted no-underline transition-colors duration-200 hover:text-txt2"
      >
        <Icon name="arrowLeft" size={14} strokeWidth={2.3} />
        All projects
      </Link>

      <GlassCard className="flex flex-wrap items-center gap-4 rounded-[20px] p-5">
        <Glyph size={46} fill={provider.fill} label={provider.letter} />

        <div className="min-w-[200px] flex-1">
          <div className="flex flex-wrap items-center gap-[10px]">
            <span className="text-[23px] font-black tracking-[-.035em]">
              {project.name}
            </span>
            {project.shared && <Pill tone="accent">Shared</Pill>}
            {project.agents.map((a) => (
              <Pill key={a} tone={agentTone(a)}>
                {AGENT_LABEL[a]}
              </Pill>
            ))}
          </div>
          <div className="mt-[5px] font-mono text-[11.5px] text-faint">
            {subtitle || project.id}
          </div>
        </div>

        <Pill
          tone={knowledgeStatusTone(label)}
          dot
          className="px-[13px] py-2 text-[12.5px] font-bold"
        >
          Knowledge: {label}
        </Pill>

        <Button
          className="h-auto rounded-button px-[15px] py-[10px]"
          icon={<Icon name="refresh" size={14} strokeWidth={2.2} />}
          onClick={load}
        >
          Reload
        </Button>
      </GlassCard>

      <div className="flex flex-wrap items-center gap-2">
        {PROJECT_TABS.map(([key, tabLabel]) => {
          const active = tab === key;
          return (
            <button
              key={key}
              type="button"
              data-surface
              aria-current={active ? "page" : undefined}
              onClick={() => setTab(key)}
              className={`cursor-pointer rounded-control-lg border px-4 py-[9px] text-[12.5px] font-bold ${
                active
                  ? "border-pb bg-pt text-p-on"
                  : "border-transparent bg-transparent text-muted hover:bg-card3"
              }`}
            >
              {tabLabel}
            </button>
          );
        })}
      </div>

      {tab === "overview" && <OverviewTab project={project} />}
      {tab === "knowledge" && (
        <KnowledgeTab project={project} onReload={load} />
      )}
      {tab === "repos" && (
        <RepositoryTab
          project={project}
          onReload={load}
          onOpenSettings={() => setTab("settings")}
        />
      )}
      {tab === "agents" && <AgentsTab project={project} />}
      {tab === "settings" && (
        <SettingsTab
          project={project}
          knowledgeStatusLabel={label}
          onOpenKnowledge={() => setTab("knowledge")}
          onReload={load}
        />
      )}
    </div>
  );
}

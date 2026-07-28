// Handoff § 3. Projects & Repositories — DETAIL STATE (`/app/projects/:id`).
//
//   "Back link `← All projects`. Header card: 46px provider glyph, name
//    23px/900, agent pills, mono `repo · branch · provider`, knowledge status
//    pill, `Refresh repository` ghost + `Re-index knowledge` primary. Tab row:
//    Overview · Project knowledge · Repository · Agents · Settings."
//
// The active tab lives in the `?tab=` QUERY PARAM — never in Zustand and never
// in the path (CLAUDE.md › "Intra-screen selection goes in query params").
// `projectId` comes from the URL via useParams for the same reason.

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  Button,
  GlassCard,
  Glyph,
  Icon,
  Pill,
  statusTone,
  toast,
} from "@/components/ui";
import { buildKnowledge, getProject, type Project } from "@/data";

import { AgentsTab } from "./AgentsTab";
import { KnowledgeTab } from "./KnowledgeTab";
import { OverviewTab } from "./OverviewTab";
import { RepositoryTab } from "./RepositoryTab";
import { SettingsTab } from "./SettingsTab";
import {
  AGENT_LABEL,
  PROJECT_TABS,
  PROVIDER_GLYPH,
  agentTone,
  isProjectTab,
  knowledgeStatus,
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
  const [loaded, setLoaded] = useState(false);
  /** Handoff › State Management › Projects › `builtKnowledge`. */
  const [justBuilt, setJustBuilt] = useState(false);

  useEffect(() => {
    let live = true;
    setLoaded(false);
    setJustBuilt(false);
    void getProject(projectId).then((p) => {
      if (!live) return;
      setProject(p);
      setLoaded(true);
    });
    return () => {
      live = false;
    };
  }, [projectId]);

  const tabParam = searchParams.get("tab");
  const tab: ProjectTab = isProjectTab(tabParam) ? tabParam : "overview";

  const setTab = (next: ProjectTab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  // An unknown :projectId falls back to the list — never guess a project.
  useEffect(() => {
    if (loaded && !project) navigate("/app/projects", { replace: true });
  }, [loaded, project, navigate]);

  if (!project) return <div ref={rootRef} />;

  const built = project.indexed || justBuilt;
  const status = knowledgeStatus(project, built);
  const provider = PROVIDER_GLYPH[project.provider];

  const onBuild = () => {
    void buildKnowledge(project.id);
    setJustBuilt(true);
    setTab("knowledge");
    toast(
      "Indexing started",
      "Both agents will pick up the new knowledge base when it finishes",
    );
  };

  return (
    <div
      ref={rootRef}
      className="flex animate-fade-in-up flex-col gap-[14px]"
    >
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
            {project.agents.map((a) => (
              <Pill key={a} tone={agentTone(a)}>
                {AGENT_LABEL[a]}
              </Pill>
            ))}
          </div>
          <div className="mt-[5px] font-mono text-[11.5px] text-faint">
            {project.repo} · {project.branch} · {project.providerName}
          </div>
        </div>

        {/* Prototype copy: "Knowledge: <status>". */}
        <Pill
          tone={statusTone(status)}
          dot
          className="px-[13px] py-2 text-[12.5px] font-bold"
        >
          Knowledge: {status}
        </Pill>

        <Button
          className="h-auto rounded-button px-[15px] py-[10px]"
          icon={<Icon name="sync" size={14} strokeWidth={2.2} />}
          onClick={() =>
            toast(
              "Repository refreshed",
              "Latest commits pulled — no structural changes detected",
            )
          }
        >
          Refresh repository
        </Button>
        <Button
          variant="primary"
          className="h-auto rounded-button px-[17px] py-[10px]"
          icon={<Icon name="spark" size={14} strokeWidth={2.2} />}
          onClick={() =>
            toast(
              "Re-index queued",
              "Knowledge base will be rebuilt from the default branch",
            )
          }
        >
          Re-index knowledge
        </Button>
      </GlassCard>

      <div className="flex flex-wrap items-center gap-2">
        {PROJECT_TABS.map(([key, label]) => {
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
              {label}
            </button>
          );
        })}
      </div>

      {tab === "overview" && <OverviewTab project={project} />}
      {tab === "knowledge" && (
        <KnowledgeTab project={project} built={built} onBuild={onBuild} />
      )}
      {tab === "repos" && <RepositoryTab project={project} />}
      {tab === "agents" && <AgentsTab project={project} />}
      {tab === "settings" && (
        <SettingsTab
          project={project}
          knowledgeStatusLabel={status}
          onOpenKnowledge={() => setTab("knowledge")}
        />
      )}
    </div>
  );
}

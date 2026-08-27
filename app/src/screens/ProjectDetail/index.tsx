// Handoff § 3. Projects & Repositories — DETAIL STATE (`/app/projects/:id`).
//
//   "Back link `← All projects`. Header card: 46px provider glyph, name
//    23px/900, agent pills, mono `repo · branch · provider`, knowledge status
//    pill … Tab row: Overview · Project knowledge · Repository · Agents ·
//    Settings."
//
// Six tabs now, not five: **Tickets** joined them in #221, because under
// containment the project's work items are a view *of the project* rather than a
// workspace-wide list to link out to (ADR 0011 §1). `PROJECT_TABS` in `shared.ts`
// is still the single source for the vocabulary; this file renders it.
//
// The active tab is a PATH SEGMENT — `/app/projects/:projectId/:tab` — never in
// Zustand and, since #219, no longer in `?tab=` either: a tab is a distinct view
// of a distinct resource, and the URL is the source of truth (CLAUDE.md ›
// Frontend conventions; ADR 0011 §1). Switching tabs is therefore a NAVIGATION
// and it PUSHES, so Back returns to the tab you came from. Old `?tab=` links are
// absorbed by `TabRedirect` on the bare project URL.
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
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import {
  Button,
  ErrorState,
  GlassCard,
  Glyph,
  Icon,
  LoadingState,
  Pill,
} from "@/components/ui";
import {
  getProject,
  getTicketCounts,
  ticketCountFor,
  type Project,
  type ProjectTicketCount,
  type TicketCounts,
} from "@/data";
import { ApiError } from "@/lib/api";

import { AgentsTab } from "./AgentsTab";
import { KnowledgeTab } from "./KnowledgeTab";
import { OverviewTab } from "./OverviewTab";
import { RepositoryTab } from "./RepositoryTab";
import { SettingsTab } from "./SettingsTab";
import { TicketsTab } from "./TicketsTab";
import {
  AGENT_LABEL,
  DEFAULT_PROJECT_TAB,
  PROJECT_TABS,
  PROVIDER_GLYPH,
  UNKNOWN_GLYPH,
  agentTone,
  isProjectTab,
  knowledgeStatus,
  knowledgeStatusTone,
  projectPath,
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
  const { projectId = "", tab: tabParam } = useParams();
  const navigate = useNavigate();
  const rootRef = useResetScrollOnMount();

  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  /**
   * Per-project ticket counts, for the Tickets tab's badge (#221).
   *
   * `getTicketCounts()` — the SAME function the sidebar tree (#220) and
   * Overview's comparison table (#218) read, which is the point: no screen
   * counts its own way, so the tab badge can never disagree with the sidebar row
   * that links to it (handoff §3, ADR 0011 §8). `null` is "unavailable" and
   * renders no badge, never a fabricated `0`.
   */
  const [counts, setCounts] = useState<TicketCounts | null>(null);

  /**
   * Re-read the project.
   *
   * `silent` is what keeps a save from looking like a page reload. This screen
   * returns early with a full-screen `LoadingState` while `status === "loading"`,
   * so a plain refetch after a save unmounts the entire tab tree — header, tabs
   * and the form the user just saved — and takes scroll position and every bit
   * of tab-local state with it. A silent refetch leaves the last-known project
   * on screen and swaps it when the answer arrives, so nothing unmounts.
   *
   * The visible mode is still right for the header's `Reload`: that is an
   * explicit "go and look again", and it should say that it is looking.
   */
  const load = useCallback((options?: { silent?: boolean }) => {
    let live = true;
    if (!options?.silent) setStatus("loading");
    void getProject(projectId)
      .then((p) => {
        if (!live) return;
        setProject(p);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (!live) return;
        // A silent refetch that fails must not tear the screen down either —
        // that would reintroduce the blanking through the back door. The user
        // still has a project on screen and the action that triggered the
        // refetch reports its own outcome, so the stale-by-seconds copy is
        // strictly better than an error page.
        if (options?.silent) return;
        setError(
          err instanceof ApiError ? err.message : "The hub did not respond.",
        );
        setStatus("error");
      });
    return () => {
      live = false;
    };
  }, [projectId]);

  useEffect(() => load(), [load]);

  // A failed count read leaves `null` — no badge at all rather than a `0` this
  // screen cannot support.
  useEffect(() => {
    let live = true;
    void getTicketCounts()
      .then((loaded) => {
        if (live) setCounts(loaded);
      })
      .catch(() => {
        if (live) setCounts(null);
      });
    return () => {
      live = false;
    };
  }, [projectId]);

  /** The header button: shows that it is working. */
  const reload = useCallback(() => load(), [load]);
  /** After a save, or when a build settles: refreshes without blanking. */
  const reloadSilently = useCallback(() => load({ silent: true }), [load]);

  const tab: ProjectTab = isProjectTab(tabParam)
    ? tabParam
    : DEFAULT_PROJECT_TAB;

  /**
   * A tab switch is a navigation, and it PUSHES on purpose: the tabs are six
   * views of the project (Tickets joined them in #221), and Back must return to
   * the previous one rather than leaving the project. (`replace` here is the trap
   * the issue calls out.)
   */
  const setTab = (next: ProjectTab) => {
    navigate(projectPath(projectId, next));
  };

  // An unknown :projectId falls back to the list — never guess a project.
  useEffect(() => {
    if (status === "ready" && !project) {
      navigate("/app/projects", { replace: true });
    }
  }, [status, project, navigate]);

  // A segment that is not a tab — a typo — resolves to the default tab rather
  // than 404ing or silently showing Overview under a URL that claims otherwise.
  // `tickets` is a tab now (#221), so it no longer lands here.
  if (!isProjectTab(tabParam)) {
    return (
      <Navigate to={projectPath(projectId, DEFAULT_PROJECT_TAB)} replace />
    );
  }

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
            onRetry={reload}
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
          onClick={reload}
        >
          Reload
        </Button>
      </GlassCard>

      <div className="flex flex-wrap items-center gap-2">
        {PROJECT_TABS.map(([key, tabLabel]) => {
          const active = tab === key;
          const count: ProjectTicketCount =
            key === "tickets" ? ticketCountFor(counts, project.rowId) : null;
          return (
            <button
              key={key}
              type="button"
              data-surface
              data-testid={`project-tab-${key}`}
              aria-current={active ? "page" : undefined}
              onClick={() => setTab(key)}
              className={`flex cursor-pointer items-center gap-2 rounded-control-lg border px-4 py-[9px] text-[12.5px] font-bold ${
                active
                  ? "border-pb bg-pt text-p-on"
                  : "border-transparent bg-transparent text-muted hover:bg-card3"
              }`}
            >
              {tabLabel}
              {/* The tri-state, rendered: `null` shows nothing at all, and the
                  `?? 0` below applies only to `undefined` — a successful read of
                  a project that holds no tickets, which is an honest zero. */}
              {key === "tickets" && count !== null && (
                <span
                  data-testid="project-tab-ticket-count"
                  className={`rounded-pill px-[7px] py-0.5 font-mono text-[10px] font-bold ${
                    active ? "bg-accent-grad text-white" : "bg-bd text-muted"
                  }`}
                >
                  {count ?? 0}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {tab === "overview" && <OverviewTab project={project} />}
      {tab === "knowledge" && (
        <KnowledgeTab project={project} onReload={reloadSilently} />
      )}
      {tab === "repos" && (
        <RepositoryTab
          project={project}
          onReload={reloadSilently}
          onOpenSettings={() => setTab("settings")}
        />
      )}
      {tab === "agents" && <AgentsTab project={project} />}
      {tab === "tickets" && (
        <TicketsTab
          project={project}
          onOpenSettings={() => setTab("settings")}
        />
      )}
      {tab === "settings" && (
        <SettingsTab
          project={project}
          knowledgeStatusLabel={label}
          onOpenKnowledge={() => setTab("knowledge")}
          onReload={reloadSilently}
        />
      )}
    </div>
  );
}

// The sidebar's project tree (#220, ADR 0011 §1 — adopted from Q-Agent's
// ADR 0015 §1, whose own tree is `../../../../q-agent/app/src/components/shell/
// SidebarProjectTree.tsx`).
//
// The project is the container, so the sidebar lists **projects**. Each row
// expands to the same tabs the project detail screen shows — `PROJECT_TABS`
// imported, never re-declared, so the tree and the tab bar cannot disagree —
// and carries the project's live ticket count.
//
// It replaces the standalone `Tickets` entry, which presented ticket-shaped data
// as a peer of Projects and threw a user out of the project they were in. The
// cross-project question that entry answered now lives on Overview
// (`screens/Overview/ProjectComparison.tsx`, #218).
//
// The Unassigned bucket is deliberately NOT a row here — the tree lists projects
// and the bucket is not one. It has its own workspace-level nav row instead
// (#221, `nav.ts`).
//
// ## Counts have exactly one source, and are never invented
//
// `ticketCountFor(counts, rowId)` over `getTicketCounts()` — the one counting
// path (#217/#218). Its tri-state is carried all the way to the pixel:
//
//   a number    the real count, in a mono badge
//   `0`         the read succeeded and this project holds no tickets. An honest
//               zero, and the only zero this row will ever render.
//   `null`      the count is unavailable (not loaded, or the fetch failed) —
//               **no badge at all**. `useSidebarStats()` was written to stop the
//               sidebar disagreeing with the page it links to; a fabricated `0`
//               on a failed read is exactly that disagreement, and it is also a
//               claim ("this project has no tickets") the app cannot support.
//
// ## Expansion is component state
//
// The URL is the source of truth for navigation (CLAUDE.md), and which rows are
// open is not navigation. `undefined` means "the user has not touched this row",
// which falls back to *the project the URL is inside* — so a cold load of
// Overview shows every row collapsed, as the handoff specifies, while a project
// URL still shows where you are. A user's own toggle always wins.
//
// Motion is the handoff's, not improvised: the only accordion motion the Motion
// tables define is `transform .22s` on the chevron (`rotate(90deg)`), plus
// `background .18–.2s` on nav rows. There is no height animation because none is
// specified. The global `prefers-reduced-motion` block in `styles/theme.css`
// neutralises both.

import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Glyph, Icon } from "@/components/ui";
import { ticketCountFor, type Project, type TicketCounts } from "@/data";
import { cn } from "@/lib/cn";
import {
  PROJECT_TABS,
  PROVIDER_GLYPH,
  UNKNOWN_GLYPH,
  projectPath,
} from "@/screens/ProjectDetail/shared";
import { useUi } from "@/store/ui";

export interface SidebarProjectTreeProps {
  /** `null` — the `GET /projects` read failed. Not the same as `[]`. */
  projects: Project[] | null;
  /** `null` — the count read failed or has not landed. No row invents a number. */
  counts: TicketCounts | null;
  loading: boolean;
  /** Called on every navigation so the shell can reset scrollTop to 0. */
  onNavigate: () => void;
}

/** Which project the URL is inside, and which of its segments. */
function useRouteProject() {
  const { pathname } = useLocation();
  const segment = pathname.match(/^\/app\/projects\/([^/]+)/)?.[1];
  return {
    routeKey: segment ? decodeURIComponent(segment) : null,
    // `tickets` lands here from both `/app/projects/:id/tickets` and
    // `/app/projects/:id/tickets/:externalId`. Since #221 it IS a tab, so the
    // Tickets row lights up on the list and stays lit on a work item's detail —
    // which is the honest answer to "where am I": still inside this project's
    // work items.
    routeTab: pathname.match(/^\/app\/projects\/[^/]+\/([^/]+)/)?.[1] ?? null,
  };
}

export function SidebarProjectTree({
  projects,
  counts,
  loading,
  onNavigate,
}: SidebarProjectTreeProps) {
  const navigate = useNavigate();
  const setModal = useUi((s) => s.setModal);
  const { routeKey, routeTab } = useRouteProject();
  const [toggled, setToggled] = useState<Record<string, boolean>>({});

  const go = (path: string) => {
    onNavigate();
    navigate(path);
  };

  if (loading) return <TreeSkeleton />;

  // A failed read says so; it does not pretend the workspace is empty.
  if (!projects) {
    return (
      <p className="px-2.5 py-2 text-[11.5px] leading-[1.45] text-faint">
        Projects unavailable
      </p>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="flex flex-col items-start gap-2 px-2.5 py-2.5">
        <span className="flex text-faint">
          <Icon name="folder" size={18} strokeWidth={2.1} />
        </span>
        <span className="text-[11.5px] leading-[1.45] text-faint">
          No projects yet. Create one to give the agents somewhere to work.
        </span>
        <button
          type="button"
          data-surface
          onClick={() => {
            onNavigate();
            navigate("/app/projects");
            setModal("project");
          }}
          className={cn(
            "cursor-pointer rounded-button border-none bg-accent-grad px-2.5 py-[6px]",
            "text-[11.5px] font-bold text-white shadow-primary",
            "transition-transform duration-200 hover:-translate-y-px",
          )}
        >
          New project
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5" data-testid="sidebar-project-tree">
      {projects.map((project) => {
        const key = project.guid || project.id;
        const current = routeKey === project.guid || routeKey === project.id;
        const open = toggled[key] ?? current;
        const glyph = project.provider
          ? PROVIDER_GLYPH[project.provider]
          : UNKNOWN_GLYPH;
        const count = ticketCountFor(counts, project.rowId);

        return (
          <div key={key} className="flex flex-col">
            <button
              type="button"
              data-surface
              data-testid="sidebar-project-row"
              data-project={key}
              aria-expanded={open}
              onClick={() => setToggled((s) => ({ ...s, [key]: !open }))}
              className={cn(
                "flex w-full cursor-pointer items-center gap-2 rounded-[11px] border px-2 py-[8px]",
                "text-left text-[12.5px] font-semibold",
                current
                  ? "border-pb bg-pt text-p-on"
                  : "border-transparent bg-transparent text-muted hover:bg-bd3",
              )}
            >
              <span
                className={cn(
                  "flex shrink-0 text-faint transition-transform duration-[.22s]",
                  open && "rotate-90",
                )}
              >
                <Icon name="chevronRight" size={12} strokeWidth={2.6} />
              </span>
              <Glyph
                size={19}
                fill={glyph.fill}
                label={glyph.letter}
                className="shrink-0"
              />
              <span className="min-w-0 flex-1 truncate">{project.name}</span>
              {/* The tri-state, rendered. `null` never reaches the badge at
                  all; the `?? 0` below applies only to `undefined`, which is a
                  successful read of a project that holds no tickets — an honest
                  zero. A failed read must never be defaulted like this. */}
              {count !== null && (
                <span
                  data-testid="sidebar-ticket-count"
                  title={
                    count === undefined || count === 0
                      ? "No tickets mirrored for this project"
                      : `${count} tickets mirrored`
                  }
                  className={cn(
                    "rounded-pill px-[7px] py-0.5 font-mono text-[10px] font-bold",
                    current
                      ? "bg-accent-grad text-white"
                      : "bg-bd text-muted",
                  )}
                >
                  {count ?? 0}
                </span>
              )}
            </button>

            {open && (
              <div className="mt-[3px] mb-[5px] ml-[15px] flex flex-col gap-px border-l border-bd2 pl-2.5">
                {PROJECT_TABS.map(([tab, label]) => {
                  const on = current && routeTab === tab;
                  return (
                    <button
                      key={tab}
                      type="button"
                      data-surface
                      data-testid={`sidebar-project-tab-${tab}`}
                      aria-current={on ? "page" : undefined}
                      onClick={() => go(projectPath(key, tab))}
                      className={cn(
                        "flex w-full cursor-pointer items-center rounded-[9px] border-none px-2.5 py-[6px]",
                        "text-left text-[12px] font-semibold",
                        on
                          ? "bg-pt text-p-on"
                          : "bg-transparent text-txt4 hover:bg-bd3",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">{label}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Three placeholder rows — the shape of the tree, with no numbers in it. */
function TreeSkeleton() {
  return (
    <div className="flex flex-col gap-1 px-2 py-1.5" aria-hidden>
      {[0, 1, 2].map((i) => (
        <span key={i} className="skeleton h-[22px] w-full rounded-[9px]" />
      ))}
    </div>
  );
}

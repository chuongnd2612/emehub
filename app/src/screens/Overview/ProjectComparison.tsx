// Handoff § 2. Overview — the **cross-project comparison table** (#218).
//
// This is the one place in the hub where a workspace-wide question can still be
// asked. Containment (ADR 0011) removes the standalone Tickets entry, and with
// it the only unscoped list; Q-Agent flagged that as the single genuine
// regression risk in the whole refactor, so this table is the guard on the
// removal rather than decoration
// (`docs/PROJECT-CONTAINMENT-HANDOFF.md` § 1, "The cross-project view must not
// be lost").
//
// One row per project: ticket source, ticket count, knowledge confidence,
// connected agents, last sync. Plus the **Unassigned** bucket as a final row —
// tickets that belong to no project must never be hidden. Read-only: nothing
// here reassigns a ticket, because tickets are a mirror (epic #223, decision 3).
//
// ## Numbers are never invented
//
// The count comes from `getTicketCounts()` — the one counting path the sidebar
// tree (#220) and the Project › Tickets tab (#221) also read, so no two screens
// can disagree. Its tri-state is preserved end to end:
//
//   a number   the real count
//   "None"     the read succeeded and the project holds no tickets
//   an em-dash the count is unavailable (not loaded, or the fetch failed)
//
// A failed fetch renders no value, never `0` — the property
// `useSidebarStats()` established and this table keeps.

import { useNavigate } from "react-router-dom";

import {
  PROVIDERS,
  ticketCountFor,
  type AgentKey,
  type Project,
  type TicketCounts,
} from "@/data";
import {
  Button,
  Glyph,
  Icon,
  Pill,
  Table,
  TableCell,
  TableEmpty,
  TableFootnote,
  TableRow,
  TableRowsSkeleton,
} from "@/components/ui";
import {
  knowledgeStatusLabelFor,
  knowledgeStatusTone,
  projectPath,
  UNASSIGNED_TICKETS_PATH,
} from "@/screens/ProjectDetail/shared";

/**
 * Grid template. It sums to the table's 1100px minimum, which is where the
 * table starts scrolling horizontally inside its own container — the page body
 * never scrolls sideways.
 */
const COLUMNS =
  "minmax(220px,2.2fr) 150px 110px 170px minmax(150px,1.2fr) 130px";

const AGENT_LABEL: Record<AgentKey, string> = {
  q: "Q-Agent",
  d: "D-Agent",
};

/** Provider key to the `Glyph` brand fill — `gh` is spelled `github` there. */
const PROVIDER_FILL = {
  ado: "azure",
  jira: "jira",
  gh: "github",
} as const;

/** A figure we do not have, said out loud rather than faked. */
function Unavailable({ reason }: { reason: string }) {
  return (
    <span className="text-faint" title={reason}>
      —
    </span>
  );
}

function SourceCell({ project }: { project: Project }) {
  if (!project.provider) {
    return (
      <TableCell>
        <span className="truncate text-faint">Not connected</span>
      </TableCell>
    );
  }
  return (
    <TableCell>
      <Glyph
        size={20}
        fill={PROVIDER_FILL[project.provider]}
        label={PROVIDERS[project.provider].glyph}
        className="shrink-0 text-[10px]"
      />
      <span className="truncate">{PROVIDERS[project.provider].name}</span>
    </TableCell>
  );
}

function KnowledgeCell({ project }: { project: Project }) {
  // A list row carries the raw `knowledgeStatus` string and a null `knowledge`
  // object; a detail read fills the object. Prefer the object, fall back to the
  // string, and read both through the project screen's own vocabulary so a
  // failed build is never softened into "needs refresh" here.
  const label = project.knowledge
    ? knowledgeStatusLabelFor(
        project.knowledge.status,
        project.knowledge.needsRefresh,
      )
    : knowledgeStatusLabelFor(project.knowledgeStatus);
  const confidence =
    project.knowledge?.confidence ?? project.knowledgeConfidence ?? 0;

  if (label === "Not indexed") {
    return (
      <TableCell>
        <span className="truncate text-faint">Not indexed</span>
      </TableCell>
    );
  }
  return (
    <TableCell>
      <span className="font-mono text-[11.5px] font-bold text-txt2">
        {confidence}%
      </span>
      {label !== "Indexed" && (
        <Pill tone={knowledgeStatusTone(label)} size="sm">
          {label}
        </Pill>
      )}
    </TableCell>
  );
}

function AgentsCell({ agents }: { agents: AgentKey[] }) {
  // The hub has no field wiring an agent to a project yet, so this is empty for
  // every live row. It reads "No agent wired" rather than blank — the same
  // words the project card uses; `data/projects.ts` says why it is empty.
  if (agents.length === 0) {
    return (
      <TableCell>
        <span className="truncate text-faint">No agent wired</span>
      </TableCell>
    );
  }
  return (
    <TableCell className="flex-wrap gap-[6px]">
      {agents.map((a) => (
        <Pill key={a} tone={a === "q" ? "qagent" : "dagent"} size="sm">
          {AGENT_LABEL[a]}
        </Pill>
      ))}
    </TableCell>
  );
}

function CountCell({
  counts,
  rowId,
}: {
  counts: TicketCounts | null;
  rowId: number;
}) {
  const count = ticketCountFor(counts, rowId);
  return (
    <TableCell mono align="end" className="pr-3">
      {count === null ? (
        <Unavailable reason="Ticket count unavailable" />
      ) : count === undefined ? (
        <span className="font-sans text-[12.5px] font-normal text-faint">
          None
        </span>
      ) : (
        <span className="text-txt2">{count.toLocaleString()}</span>
      )}
    </TableCell>
  );
}

export function ProjectComparison({
  projects,
  counts,
  loading = false,
}: {
  projects: Project[];
  /** `null` — not loaded, or the read failed. No cell may invent a number. */
  counts: TicketCounts | null;
  loading?: boolean;
}) {
  const navigate = useNavigate();

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-[10px]">
        <span className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
          Every project at a glance
        </span>
        <button
          type="button"
          data-surface
          onClick={() => navigate("/app/projects")}
          className="ml-auto cursor-pointer border-none bg-transparent p-0 text-[11.5px] font-semibold text-ps-text"
        >
          All projects
        </button>
      </div>

      <Table>
        <TableRow columns={COLUMNS} header>
          <TableCell>PROJECT</TableCell>
          <TableCell>TICKET SOURCE</TableCell>
          <TableCell align="end" className="pr-3">
            WORK ITEMS
          </TableCell>
          <TableCell>KNOWLEDGE</TableCell>
          <TableCell>AGENTS</TableCell>
          <TableCell>LAST SYNC</TableCell>
        </TableRow>

        {loading ? (
          <TableRowsSkeleton rows={3} columns={6} />
        ) : projects.length === 0 ? (
          <TableEmpty
            icon="folder"
            message="No projects yet — a project is what gives work items, a repository and a knowledge base somewhere to live."
            action={
              <Button size="sm" onClick={() => navigate("/app/projects")}>
                New project
              </Button>
            }
          />
        ) : (
          <>
            {projects.map((p) => (
              <TableRow
                key={p.id}
                columns={COLUMNS}
                interactive
                onClick={() =>
                  navigate(projectPath(p.guid || p.id))
                }
              >
                <TableCell>
                  <Glyph
                    size={26}
                    gradient={p.gradient}
                    label={p.initials}
                    className="shrink-0 text-[10px]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-bold text-txt2">
                      {p.name}
                    </span>
                    <span className="block truncate font-mono text-[10px] text-label">
                      {p.repo || p.id}
                    </span>
                  </span>
                </TableCell>

                <SourceCell project={p} />
                <CountCell counts={counts} rowId={p.rowId} />
                <KnowledgeCell project={p} />
                <AgentsCell agents={p.agents} />

                <TableCell mono>
                  {p.lastSynced ? (
                    <span className="truncate text-txt3">{p.lastSynced}</span>
                  ) : (
                    <span className="font-sans text-[12.5px] font-normal text-faint">
                      Never
                    </span>
                  )}
                </TableCell>
              </TableRow>
            ))}

            {/* The Unassigned bucket. Rendered only when it holds something — a
                zero bucket is furniture — and never omitted when it does,
                because those work items exist and belong to no row above. */}
            {counts !== null && counts.unassigned > 0 && (
              <TableRow
                columns={COLUMNS}
                className="bg-inset"
                interactive
                // The bucket is a real screen as of #221, so this row is a way
                // in rather than a dead statistic.
                onClick={() => navigate(UNASSIGNED_TICKETS_PATH)}
              >
                <TableCell>
                  <span className="flex size-[26px] shrink-0 items-center justify-center rounded-glyph border border-bd2 bg-bd3 text-txt4">
                    <Icon name="ticket" size={13} strokeWidth={2.2} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-bold text-txt2">
                      Unassigned
                    </span>
                    <span className="block truncate text-[10px] text-label">
                      Work items that belong to no project
                    </span>
                  </span>
                </TableCell>
                <TableCell>
                  <Unavailable reason="No project, so no configured source" />
                </TableCell>
                <TableCell mono align="end" className="pr-3">
                  <span className="text-txt2">
                    {counts.unassigned.toLocaleString()}
                  </span>
                </TableCell>
                <TableCell>
                  <Unavailable reason="Knowledge is per project" />
                </TableCell>
                <TableCell>
                  <Unavailable reason="Agents are wired per project" />
                </TableCell>
                <TableCell>
                  <Unavailable reason="No project, so no project sync" />
                </TableCell>
              </TableRow>
            )}
          </>
        )}
      </Table>

      <TableFootnote>
        Work items are a read-only mirror of the provider. Every count on this
        page comes from one query, so this table, the sidebar and each project
        always agree.
      </TableFootnote>
    </section>
  );
}

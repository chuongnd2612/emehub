// Handoff § 3. Projects › detail › Project knowledge.
//
//   "if not indexed: dashed empty state with a book glyph and a `Build project
//    knowledge` primary CTA … If indexed: 'What the agents learned' accordion
//    with a chevron that rotates 90° when open; then a source toolbar and a
//    7-column source table."
//
// ## Two deliberate departures, both because the hub cannot honour the design
//
// 1. **There is no `Build project knowledge` button.** Building means cloning
//    the repository and running `project-bootstrap` through the Claude CLI,
//    which needs a filesystem and a credential on disk. EmeHub has neither, and
//    handing out the repository PAT to make it possible is what CLAUDE.md
//    forbids. The agent builds on its own host and reports the result with
//    `PUT /projects/{key}/repos/{repo}/knowledge` (ROADMAP.md Phase 4). The
//    empty state says exactly that and offers `Check again`, which really does
//    re-read the row — the useful action when an agent has since reported one.
//
// 2. **There is no source table.** Nothing in the hub models the handoff's
//    source rows (icon, title, type, size, chunks, scope, state);
//    `getKnowledgeSources` has no endpoint behind it and resolves to `[]`.
//    Rendering the fixtures would be showing invented rows as live data, so the
//    toolbar and table appear only if that call ever returns something, and a
//    notice explains the gap until it does.
//
// The accordion IS real: it is rendered from the `knowledge` blob the agent
// reported (`data/knowledge.ts › knowledgeSections`).

import { useEffect, useMemo, useState } from "react";

import {
  AccordionItem,
  Button,
  GlassCard,
  Icon,
  Input,
  Notice,
  StatusPill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  toast,
} from "@/components/ui";
import {
  getKnowledgeSources,
  knowledgeSections,
  type KnowledgeSource,
  type KnowledgeSourceType,
  type Project,
} from "@/data";
import { useUi } from "@/store/ui";
import { SOURCE_TYPE_CHIP, SOURCE_TYPES, chunkLabel, isBuilt } from "./shared";

/** Handoff › source table — `34px | 2.6fr | 110 | 100 | 120 | 110 | 100`. */
const COLUMNS = "34px minmax(0,2.6fr) 110px 100px 120px 110px 100px";

function TypeChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-surface
      onClick={onClick}
      className={`cursor-pointer rounded-[10px] border px-[14px] py-[7px] text-[12px] font-bold ${
        active
          ? "border-pb bg-pt text-p-on"
          : "border-bd bg-inset text-muted hover:bg-card3"
      }`}
    >
      {label}
    </button>
  );
}

/** Not indexed — the honest version of the handoff's dashed empty state. */
function NotIndexed({
  project,
  onReload,
}: {
  project: Project;
  onReload: () => void;
}) {
  const knowledge = project.knowledge;
  const failed = knowledge?.status === "error";
  const building = knowledge?.status === "indexing";

  return (
    <div className="flex flex-col gap-[14px]">
      <div className="flex flex-col items-center gap-[11px] rounded-[20px] border border-dashed border-bd2 bg-inset px-[30px] py-[48px] text-center">
        <span className="flex size-[46px] items-center justify-center rounded-glyph-lg border border-pb bg-pt text-ps-text">
          <Icon name="book" size={22} strokeWidth={2.1} />
        </span>
        <div className="text-[15.5px] font-extrabold tracking-[-.02em]">
          {building ? "A build is in progress" : "No knowledge base yet"}
        </div>
        <p className="m-0 max-w-[440px] text-[12.5px] text-pretty text-muted">
          {building
            ? "An agent is indexing this repository on its own host. The result lands here as soon as it reports back."
            : "Once an agent indexes this repository, EmeHub keeps the versioned result here and every agent you launch inherits it."}
        </p>
        <Button
          variant="primary"
          className="mt-[6px] h-auto rounded-button px-[22px] py-3 text-[13.5px]"
          icon={<Icon name="refresh" size={15} strokeWidth={2.2} />}
          onClick={onReload}
        >
          Check again
        </Button>
      </div>

      {failed && knowledge?.lastError && (
        <Notice tone="danger">
          The last build failed: {knowledge.lastError}
        </Notice>
      )}

      <Notice tone="info">
        EmeHub records knowledge, it does not build it. Cloning{" "}
        {project.repo || "the repository"} and running the indexing skill needs
        a checkout and a Claude credential on disk — both live on the agent
        host, which reports the finished index back to the hub.
      </Notice>
    </div>
  );
}

export function KnowledgeTab({
  project,
  onReload,
}: {
  project: Project;
  onReload: () => void;
}) {
  const setModal = useUi((s) => s.setModal);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [openKeys, setOpenKeys] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<KnowledgeSourceType | "All">("All");

  const knowledge = project.knowledge;
  const sections = useMemo(() => knowledgeSections(knowledge), [knowledge]);

  useEffect(() => {
    let live = true;
    void getKnowledgeSources(project.id).then((rows) => {
      if (live) setSources(rows);
    });
    return () => {
      live = false;
    };
  }, [project.id]);

  // Handoff filtering rule: type chip AND a title match on the query.
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sources.filter(
      (k) =>
        (filter === "All" || k.type === filter) &&
        (!q || k.title.toLowerCase().includes(q)),
    );
  }, [sources, filter, query]);

  if (!isBuilt(knowledge) || !knowledge) {
    return <NotIndexed project={project} onReload={onReload} />;
  }

  return (
    <div className="flex flex-col gap-[14px]">
      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="flex items-center gap-[10px]">
          <div className="flex-1">
            <div className="text-[15px] font-extrabold tracking-[-.01em]">
              What the agents learned
            </div>
            <div className="mt-1 text-[12.5px] text-muted">
              Indexed from {knowledge.repo || project.repo || project.id}
              {project.branch ? ` · ${project.branch}` : ""} ·{" "}
              {knowledge.lastIndexedLabel}
            </div>
          </div>
          <span className="rounded-pill border border-pb bg-pt px-[10px] py-1 font-mono text-[11px] font-semibold text-ps-text">
            {knowledge.version}
          </span>
        </div>

        <div className="mt-3 flex flex-col gap-2">
          {sections.map((s) => (
            <AccordionItem
              key={s.key}
              itemKey={s.key}
              title={s.label}
              open={openKeys.includes(s.key)}
              onToggle={(key) =>
                setOpenKeys((keys) =>
                  keys.includes(key)
                    ? keys.filter((k) => k !== key)
                    : [...keys, key],
                )
              }
            >
              <p className="m-0 text-pretty">{s.body}</p>
            </AccordionItem>
          ))}
        </div>

        {sections.length === 0 && (
          <Notice tone="warn" className="mt-3">
            This knowledge base is indexed but the agent reported an empty
            payload — there is nothing for the agents to read yet.
          </Notice>
        )}
      </GlassCard>

      {sources.length === 0 ? (
        <Notice tone="info">
          EmeHub stores one knowledge record per repository, not a library of
          individual documents. There is no source registry behind the hub yet,
          so nothing is listed here.
        </Notice>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-[10px]">
            <Input
              className="h-auto max-w-[340px] flex-1 rounded-button px-[15px] py-[10px]"
              icon={
                <span className="text-ps-text">
                  <Icon name="search" size={15} strokeWidth={2.2} />
                </span>
              }
              placeholder="Search this project's sources"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              {SOURCE_TYPES.map((t) => (
                <TypeChip
                  key={t}
                  label={t}
                  active={filter === t}
                  onClick={() => setFilter(t)}
                />
              ))}
            </div>
            <Button
              variant="primary"
              className="ml-auto h-auto rounded-button px-[18px] py-[11px] text-[13px]"
              icon={<Icon name="plus" size={15} strokeWidth={2.6} />}
              onClick={() => setModal("knowledge")}
            >
              Add source
            </Button>
          </div>

          <Table className="rounded-[20px] p-0">
            <TableRow columns={COLUMNS} header>
              <span />
              <span>SOURCE</span>
              <span>TYPE</span>
              <span>SIZE</span>
              <span>CHUNKS</span>
              <span>SCOPE</span>
              <span className="text-right">STATE</span>
            </TableRow>

            {rows.map((k) => {
              const chip = SOURCE_TYPE_CHIP[k.type];
              return (
                <TableRow
                  key={k.id}
                  columns={COLUMNS}
                  interactive
                  onClick={() => toast(k.title, `${k.type} · ${k.scope}`, "info")}
                >
                  <span
                    className={`flex size-8 shrink-0 items-center justify-center rounded-[10px] border border-current/20 ${chip.className}`}
                  >
                    <Icon name={chip.icon} size={15} strokeWidth={2.2} />
                  </span>
                  <TableCell className="block truncate">
                    <span className="block truncate text-[13px] font-bold text-txt2">
                      {k.title}
                    </span>
                    <span className="mt-[3px] block font-mono text-[10px] text-label">
                      {k.id}
                    </span>
                  </TableCell>
                  <TableCell className="text-[11.5px] font-semibold text-txt4">
                    {k.type}
                  </TableCell>
                  <TableCell mono className="text-muted">
                    {k.size}
                  </TableCell>
                  <TableCell className="text-[11.5px] text-muted">
                    {chunkLabel(k.chunks)}
                  </TableCell>
                  <TableCell className="text-[11.5px] text-muted">
                    {k.scope}
                  </TableCell>
                  <TableCell align="end">
                    <StatusPill status={k.indexed ? "Indexed" : "Pending"} />
                  </TableCell>
                </TableRow>
              );
            })}

            {rows.length === 0 && (
              <TableEmpty message="No sources match this filter." />
            )}
          </Table>
        </>
      )}
    </div>
  );
}

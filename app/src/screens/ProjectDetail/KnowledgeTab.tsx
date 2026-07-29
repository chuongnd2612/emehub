// Handoff § 3. Projects › detail › Project knowledge.
//
//   "if not indexed: dashed empty state with a book glyph and a `Build project
//    knowledge` primary CTA … If indexed: 'What the agents learned' accordion
//    with a chevron that rotates 90° when open; then a source toolbar and a
//    7-column source table."
//
// ## The `Build project knowledge` CTA is real (ADR 0007)
//
// It used to be absent, because the hub could not clone a repository or run
// `project-bootstrap`. ADR 0007 gave it both, so the handoff's primary CTA is
// back and does what it says: `POST …/knowledge/build` returns `202` with the
// row at `indexing`, and this tab polls until the status settles. A build needs
// a repository to clone, so the CTA is disabled with an explanation when the
// project has no configured repo.
//
// One departure remains. **There is no source table.** Nothing in the hub models
// the handoff's source rows (icon, title, type, size, chunks, scope, state);
// `getKnowledgeSources` has no endpoint behind it and resolves to `[]`.
// Rendering the fixtures would be showing invented rows as live data, so the
// toolbar and table appear only if that call ever returns something, and a
// notice explains the gap until it does.
//
// The accordion IS real: it is rendered from the `knowledge` blob
// (`data/knowledge.ts › knowledgeSections`).

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
  buildKnowledge,
  getKnowledgeSources,
  knowledgeSections,
  type KnowledgeSource,
  type KnowledgeSourceType,
  type Project,
} from "@/data";
import { ApiError } from "@/lib/api";
import { useUi } from "@/store/ui";
import { SOURCE_TYPE_CHIP, SOURCE_TYPES, chunkLabel, isBuilt } from "./shared";

/**
 * How often an in-flight build is re-checked. A build is minutes long and the
 * hub caps how many run at once, so a tighter interval would only add load
 * without telling the user anything sooner.
 */
const POLL_MS = 5000;

/**
 * Re-read the project while a build is in flight, so `indexing` settles into
 * `indexed` or `error` without the user reaching for the button.
 */
function useBuildPolling(building: boolean, onReload: () => void) {
  useEffect(() => {
    if (!building) return;
    const timer = window.setInterval(onReload, POLL_MS);
    return () => window.clearInterval(timer);
  }, [building, onReload]);
}

/**
 * Start a build and report it. Resolves when the row reaches `indexing`, not
 * when the build finishes — the polling above carries it from there.
 */
function useStartBuild(project: Project, onReload: () => void) {
  const [starting, setStarting] = useState(false);

  const start = () => {
    setStarting(true);
    void buildKnowledge(project.id, project.repo)
      .then(() => {
        toast(
          "Build started",
          `EmeHub is indexing ${project.repo || project.id}. This takes a few minutes.`,
          "info",
        );
        onReload();
      })
      .catch((error: unknown) => {
        toast(
          "Could not start the build",
          error instanceof ApiError ? error.message : "The hub did not respond.",
          "warn",
        );
      })
      .finally(() => setStarting(false));
  };

  return { starting, start };
}

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

/** Not indexed — the handoff's dashed empty state, with a CTA that works. */
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
  const { starting, start } = useStartBuild(project, onReload);

  useBuildPolling(building, onReload);

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
            ? "EmeHub is cloning the repository and indexing it. This takes a few minutes; the result appears here on its own."
            : "Index this repository once and every agent you launch inherits the versioned result."}
        </p>
        {building ? (
          <Button
            variant="primary"
            className="mt-[6px] h-auto rounded-button px-[22px] py-3 text-[13.5px]"
            icon={<Icon name="refresh" size={15} strokeWidth={2.2} />}
            onClick={onReload}
          >
            Check again
          </Button>
        ) : (
          <Button
            variant="primary"
            className="mt-[6px] h-auto rounded-button px-[22px] py-3 text-[13.5px]"
            icon={<Icon name="book" size={15} strokeWidth={2.2} />}
            onClick={start}
            disabled={starting || !project.repo}
          >
            {starting ? "Starting…" : "Build project knowledge"}
          </Button>
        )}
      </div>

      {failed && knowledge?.lastError && (
        <Notice tone="danger">
          The last build failed: {knowledge.lastError}
        </Notice>
      )}

      {!project.repo && (
        <Notice tone="warn">
          Add a repository under Settings before building — EmeHub clones it to
          index the code.
        </Notice>
      )}
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
  const { starting, start } = useStartBuild(project, onReload);
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
          {/* Rebuild, not "Re-index queued": this really starts one, and the
              version increments when it lands (ADR 0007). */}
          <Button
            className="h-auto rounded-button px-[16px] py-[9px] text-[12.5px]"
            icon={<Icon name="refresh" size={14} strokeWidth={2.2} />}
            onClick={start}
            disabled={starting || !project.repo}
          >
            {starting ? "Starting…" : "Rebuild"}
          </Button>
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

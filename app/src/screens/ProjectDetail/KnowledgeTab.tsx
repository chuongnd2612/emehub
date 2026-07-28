// Handoff § 3. Projects › detail › Project knowledge.
//
//   "if not indexed: dashed empty state with a book glyph and a `Build project
//    knowledge` primary CTA (starts indexing, toasts, switches to this tab).
//    If indexed: 'What the agents learned' accordion (4 sections) with a
//    chevron that rotates 90° when open; then a source toolbar (search + type
//    chips All/Markdown/Document/URL/File + `Add source`) and a 7-column source
//    table (icon, title+mono id, type, size, chunks, scope, state pill) with an
//    empty state."

import { useEffect, useMemo, useState } from "react";

import {
  AccordionItem,
  Button,
  GlassCard,
  Icon,
  Input,
  StatusPill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  toast,
} from "@/components/ui";
import {
  getKnowledgeSections,
  getKnowledgeSources,
  type KnowledgeSection,
  type KnowledgeSource,
  type KnowledgeSourceType,
  type Project,
} from "@/data";
import { useUi } from "@/store/ui";
import { SOURCE_TYPE_CHIP, SOURCE_TYPES, chunkLabel } from "./shared";

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

function EmptyState({ onBuild }: { onBuild: () => void }) {
  return (
    <div className="flex flex-col items-center gap-[11px] rounded-[20px] border border-dashed border-bd2 bg-inset px-[30px] py-[48px] text-center">
      <span className="flex size-[46px] items-center justify-center rounded-glyph-lg border border-pb bg-pt text-ps-text">
        <Icon name="book" size={22} strokeWidth={2.1} />
      </span>
      <div className="text-[15.5px] font-extrabold tracking-[-.02em]">
        No knowledge base yet
      </div>
      <p className="m-0 max-w-[420px] text-[12.5px] text-pretty text-muted">
        EmeHub reads the repository once and keeps a versioned index of
        architecture, conventions and fixtures. Every agent you launch inherits
        it.
      </p>
      <Button
        variant="primary"
        className="mt-[6px] h-auto rounded-button px-[22px] py-3 text-[13.5px]"
        icon={<Icon name="spark" size={15} strokeWidth={2.2} />}
        onClick={onBuild}
      >
        Build project knowledge
      </Button>
    </div>
  );
}

export function KnowledgeTab({
  project,
  built,
  onBuild,
}: {
  project: Project;
  built: boolean;
  onBuild: () => void;
}) {
  const setModal = useUi((s) => s.setModal);
  const [sections, setSections] = useState<KnowledgeSection[]>([]);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [openKeys, setOpenKeys] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<KnowledgeSourceType | "All">("All");

  useEffect(() => {
    let live = true;
    void getKnowledgeSections(project.id).then((rows) => {
      if (live) setSections(rows);
    });
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

  if (!built) return <EmptyState onBuild={onBuild} />;

  return (
    <div className="flex flex-col gap-[14px]">
      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="flex items-center gap-[10px]">
          <div className="flex-1">
            <div className="text-[15px] font-extrabold tracking-[-.01em]">
              What the agents learned
            </div>
            <div className="mt-1 text-[12.5px] text-muted">
              Indexed from {project.repo} · {project.branch} ·{" "}
              {project.lastIndexed}
            </div>
          </div>
          <span className="rounded-pill border border-pb bg-pt px-[10px] py-1 font-mono text-[11px] font-semibold text-ps-text">
            {project.knowledgeVersion}
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
      </GlassCard>

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
    </div>
  );
}

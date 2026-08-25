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
// One departure remains. **There is no source table** (#191). Nothing in the hub
// models the handoff's source rows (icon, title, type, size, chunks, scope,
// state), so the toolbar, the search box, the type chips, the table and the
// "Add source" button are gone rather than dormant — they hung off a
// `getKnowledgeSources` stub that returned `[]`, which made every one of them
// unreachable, and the "Add source" modal behind the button posted nothing at
// all. A notice states the gap instead.
//
// The accordion IS real: it is rendered from the `knowledge` blob
// (`data/knowledge.ts › knowledgeSections`).

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AccordionItem,
  Button,
  GlassCard,
  Icon,
  Notice,
  toast,
} from "@/components/ui";
import {
  buildKnowledge,
  getRepoKnowledge,
  knowledgeSections,
  type KnowledgeMeta,
  type Project,
} from "@/data";
import { ApiError } from "@/lib/api";
import { BuildProgress } from "./BuildProgress";
import { isBuilt } from "./shared";

/**
 * How often an in-flight build is re-checked.
 *
 * 2000 ms, matching the interval Q-Agent really polls at — the one part of its
 * build experience that was never theatre. It is only paid while a build is
 * running, and it is the *only* thing that ends the loading state (issue #68).
 */
const POLL_MS = 2000;

/**
 * The whole build lifecycle, in one place, because its three rules are the
 * point of issue #68 and separating them is how Q-Agent lost them:
 *
 * 1. **The loading state ends when the polled status leaves `indexing`.** Never
 *    on the POST response — that response only means the row was enqueued, and
 *    Q-Agent closing its overlay on it is why its overlay's duration correlates
 *    with HTTP latency instead of with the build.
 * 2. **The success toast fires on real completion.** It is raised by the
 *    transition `indexing → indexed|error` observed in a poll, so it can only
 *    happen after the hub has actually written a knowledge base.
 * 3. **An orphaned row is not a build.** `build.orphaned` says the hub restarted
 *    while this row was `indexing`; polling stops and the card offers a retry.
 *
 * Polling reads the knowledge row directly rather than calling `onReload`, so
 * the surrounding screen is not thrown back into its loading state twice a
 * second. `onReload` is called once, when the build settles.
 */
function useBuildLifecycle(project: Project, onReload: () => void) {
  const [knowledge, setKnowledge] = useState<KnowledgeMeta | null>(
    project.knowledge,
  );
  const [starting, setStarting] = useState(false);
  const previousStatus = useRef(project.knowledge?.status);

  // A parent re-read (the header's Reload, a route change) is authoritative.
  useEffect(() => {
    setKnowledge(project.knowledge);
    previousStatus.current = project.knowledge?.status;
  }, [project.knowledge]);

  const building =
    knowledge?.status === "indexing" && !knowledge.build.orphaned;

  useEffect(() => {
    if (!building) return;
    let live = true;
    const timer = window.setInterval(() => {
      void getRepoKnowledge(project.id, project.repo)
        .then((next) => {
          if (live && next) setKnowledge(next);
        })
        .catch(() => {
          /* A dropped poll is not a build failure; the next tick retries. */
        });
    }, POLL_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [building, project.id, project.repo]);

  // Rules 1 and 2: everything terminal hangs off this observed transition.
  useEffect(() => {
    const status = knowledge?.status;
    const was = previousStatus.current;
    previousStatus.current = status;
    if (!status || was !== "indexing" || status === "indexing") return;

    if (status === "error") {
      toast(
        "The build failed",
        "warn",
        knowledge?.lastError || "The hub did not say why.",
      );
    } else {
      toast("Project knowledge built");
    }
    onReload();
  }, [knowledge, onReload, project.id, project.repo]);

  /**
   * Start a build. The toast says *started*, because that is all that has
   * happened: the hub answers 202 with the row at `indexing`, stage `queued`.
   */
  const start = useCallback(() => {
    setStarting(true);
    void buildKnowledge(project.id, project.repo)
      .then((next) => {
        toast("Build started", "info");
        // The enqueue response IS the row, at `indexing`/`queued` — adopting it
        // starts the stepper without claiming anything was built.
        setKnowledge(next);
      })
      .catch((error: unknown) => {
        toast(
          "Could not start the build",
          "warn",
          error instanceof ApiError
            ? error.message
            : "The hub did not respond.",
        );
      })
      .finally(() => setStarting(false));
  }, [project.id, project.repo]);

  return { knowledge, building, starting, start };
}

/**
 * Not indexed — the handoff's dashed empty state, with a CTA that works.
 *
 * While a build is running the dashed panel is replaced by the live stepper:
 * the handoff's empty state is for "there is nothing here", and during a build
 * there very much is.
 */
function NotIndexed({
  project,
  knowledge,
  building,
  starting,
  start,
}: {
  project: Project;
  knowledge: KnowledgeMeta | null;
  building: boolean;
  starting: boolean;
  start: () => void;
}) {
  const failed = knowledge?.status === "error";
  const orphaned =
    knowledge?.status === "indexing" && knowledge.build.orphaned === true;

  return (
    <div className="flex flex-col gap-[14px]">
      {building || orphaned ? (
        <BuildProgress
          build={knowledge!.build}
          repo={project.repo}
          onRetry={start}
          retrying={starting}
        />
      ) : (
        <div className="flex flex-col items-center gap-[11px] rounded-[20px] border border-dashed border-bd2 bg-inset px-[30px] py-[48px] text-center">
          <span className="flex size-[46px] items-center justify-center rounded-glyph-lg border border-pb bg-pt text-ps-text">
            <Icon name="book" size={22} strokeWidth={2.1} />
          </span>
          <div className="text-[15.5px] font-extrabold tracking-[-.02em]">
            No knowledge base yet
          </div>
          <p className="m-0 max-w-[440px] text-[12.5px] text-pretty text-muted">
            Index this repository once and every agent you launch inherits the
            versioned result.
          </p>
          <Button
            variant="primary"
            className="mt-[6px] h-auto rounded-button px-[22px] py-3 text-[13.5px]"
            icon={<Icon name="book" size={15} strokeWidth={2.2} />}
            onClick={start}
            disabled={starting || !project.repo}
          >
            {starting ? "Starting…" : "Build project knowledge"}
          </Button>
        </div>
      )}

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
  const { knowledge, building, starting, start } = useBuildLifecycle(
    project,
    onReload,
  );
  const [openKeys, setOpenKeys] = useState<string[]>([]);

  const sections = useMemo(() => knowledgeSections(knowledge), [knowledge]);

  // A *rebuild* keeps the built view: the previous knowledge base is still the
  // truth until the new one lands, so the accordion stays and the stepper goes
  // above it. Only a first build falls back to the empty state.
  const rebuilding = building && knowledge?.lastIndexed != null;

  if (!knowledge || (!isBuilt(knowledge) && !rebuilding)) {
    return (
      <NotIndexed
        project={project}
        knowledge={knowledge}
        building={building}
        starting={starting}
        start={start}
      />
    );
  }

  return (
    <div className="flex flex-col gap-[14px]">
      {/* A rebuild of an already-indexed base keeps the accordion visible and
          puts the live stepper above it — the old knowledge is still the truth
          until the new one lands. */}
      {building && (
        <BuildProgress
          build={knowledge.build}
          repo={project.repo}
          onRetry={start}
          retrying={starting}
        />
      )}
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

      <Notice tone="info">
        EmeHub stores one knowledge record per repository, not a library of
        individual documents. There is no source registry behind the hub yet,
        so nothing is listed here.
      </Notice>
    </div>
  );
}

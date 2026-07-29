// The knowledge-build stepper (issue #68).
//
// Q-Agent's `KnowledgeBuildOverlay` is the look this borrows and the behaviour
// it refuses. Its checklist advances on a 620 ms `setInterval` that is connected
// to nothing, saturates in ~5.6 s and then spins for the remaining minutes; it
// closes on the POST response and toasts "built" before the build has produced
// anything.
//
// Everything here is read from the row instead:
//
//   • the completed / current / pending split comes from `build.step` against
//     `build.totalSteps`, both written by the worker before it does the work;
//   • the line under the current stage is `build.message` — during `analyzing`
//     that is derived from the Claude CLI's own event stream, so it names the
//     file being read;
//   • the elapsed clock counts from `build.startedAt`, a real timestamp, so a
//     reload shows the true age of the build rather than restarting at zero;
//   • `build.orphaned` means the row says `indexing` with no worker behind it
//     (a container restarted mid-build). That gets a retry, never a spinner.
//
// It renders inline, in the panel the tab already had, rather than as a
// full-screen modal: the progress survives a reload because it lives on the
// row, and an overlay that reappears on every visit would be in the way of the
// thing it is describing. No overlay means nothing to portal.

import { useEffect, useState } from "react";

import { Button, Icon, Notice, Spinner } from "@/components/ui";
import {
  KNOWLEDGE_BUILD_LABELS,
  KNOWLEDGE_BUILD_STAGES,
  type KnowledgeBuildProgress,
} from "@/data";

/** `1:04` / `12:31` — mm:ss, because a build is minutes, not hours. */
function elapsedLabel(startedAt: string | null, now: number): string {
  if (!startedAt) return "";
  const started = Date.parse(startedAt);
  if (Number.isNaN(started)) return "";
  const seconds = Math.max(0, Math.floor((now - started) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * A once-per-second tick, only while it is needed.
 *
 * This is a clock, not an animation: it reports elapsed real time and is the
 * one thing on this card that would be wrong if it stopped, so it is not gated
 * by `prefers-reduced-motion`. Everything that *is* animation — the spinner —
 * is already neutralised globally by the reduced-motion block in `theme.css`.
 */
function useSecondsTick(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function StageRow({
  label,
  state,
  message,
}: {
  label: string;
  state: "done" | "current" | "pending";
  message?: string;
}) {
  return (
    <li className="flex items-start gap-[13px] py-[7px]">
      <span className="mt-[1px] flex size-[22px] shrink-0 items-center justify-center">
        {state === "done" && (
          <span className="flex size-[22px] items-center justify-center rounded-full bg-ok-tint text-ok">
            <Icon name="check" size={13} strokeWidth={3} />
          </span>
        )}
        {state === "current" && <Spinner size={20} speed="index" className="text-pl" />}
        {state === "pending" && (
          <span className="size-[9px] rounded-full border border-bd2 bg-inset" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={
            state === "current"
              ? "block text-[13.5px] font-bold text-txt2"
              : state === "done"
                ? "block text-[13.5px] text-muted"
                : "block text-[13.5px] text-faint"
          }
        >
          {label}
        </span>
        {/* The hub sends the stage's own label as the message until something
            more specific arrives (the first Claude event, the repo name).
            Repeating it under itself is noise, so it only shows once it says
            something the label does not. */}
        {state === "current" && message && message !== label && (
          <span
            className="mt-[3px] block truncate font-mono text-[11px] text-label"
            title={message}
          >
            {message}
          </span>
        )}
      </span>
    </li>
  );
}

export interface BuildProgressProps {
  build: KnowledgeBuildProgress;
  /** Repository being indexed, for the subtitle. */
  repo: string;
  /** Start a fresh build — offered only when the current one is orphaned. */
  onRetry: () => void;
  retrying?: boolean;
}

/**
 * Live build progress, driven entirely by the polled row.
 *
 * `step` is 1-based and 0 means "nothing recorded yet" — a row an agent set to
 * `indexing` through `PUT`, or a pre-#68 row. That case gets an honest line
 * saying the hub has no stage for it, not a stepper stuck at step one.
 */
export function BuildProgress({
  build,
  repo,
  onRetry,
  retrying,
}: BuildProgressProps) {
  const now = useSecondsTick(!build.orphaned);
  const elapsed = elapsedLabel(build.startedAt, now);

  if (build.orphaned) {
    return (
      <div className="flex flex-col gap-[14px]">
        <Notice tone="warn">
          This build stopped without finishing — the hub restarted while it was
          running, so nothing is working on it now. Start it again to pick up
          where it left off.
        </Notice>
        <div className="flex justify-center">
          <Button
            variant="primary"
            className="h-auto rounded-button px-[22px] py-3 text-[13.5px]"
            icon={<Icon name="refresh" size={15} strokeWidth={2.2} />}
            onClick={onRetry}
            disabled={retrying}
          >
            {retrying ? "Starting…" : "Build again"}
          </Button>
        </div>
      </div>
    );
  }

  const stages = KNOWLEDGE_BUILD_STAGES.slice(0, build.totalSteps);
  const current = build.step;

  return (
    <div
      className="flex flex-col gap-[14px] rounded-[20px] border border-bd2 bg-inset px-[26px] py-[24px]"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-[13px]">
        <span className="flex size-[46px] shrink-0 items-center justify-center rounded-glyph-lg border border-pb bg-pt text-ps-text">
          <Icon name="book" size={22} strokeWidth={2.1} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[15.5px] font-extrabold tracking-[-.02em]">
            Building the knowledge base
          </div>
          <div className="mt-[2px] truncate text-[12.5px] text-muted">
            {repo ? `${repo} · ` : ""}
            {current > 0
              ? `step ${current} of ${build.totalSteps}`
              : "waiting for the first stage"}
          </div>
        </div>
        {elapsed && (
          <span className="shrink-0 rounded-pill border border-bd bg-card3 px-[10px] py-1 font-mono text-[11px] font-semibold text-txt4">
            {elapsed}
          </span>
        )}
      </div>

      {current > 0 ? (
        <ul className="m-0 flex list-none flex-col p-0">
          {stages.map((stage, i) => {
            const ordinal = i + 1;
            return (
              <StageRow
                key={stage}
                label={KNOWLEDGE_BUILD_LABELS[stage]}
                state={
                  ordinal < current
                    ? "done"
                    : ordinal === current
                      ? "current"
                      : "pending"
                }
                message={build.message}
              />
            );
          })}
        </ul>
      ) : (
        <p className="m-0 text-[12.5px] text-pretty text-muted">
          This row is marked as indexing, but no stage has been recorded against
          it — an agent is building it on its own host. The result appears here
          when it reports back.
        </p>
      )}
    </div>
  );
}

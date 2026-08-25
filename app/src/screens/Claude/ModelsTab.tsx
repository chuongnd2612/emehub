// Handoff › 6. Claude Settings › Models — "default model + fast model dropdown
// cards, thinking-level chips (Off/Low/Medium/High) with an explanatory line,
// and a `Parallel agent runs` range (1–8)".
//
// **Three of those four are gone**, all for the same reason (#190, #197): this
// tab's whole problem was controls that could not do the thing they named.
//
//   • `Parallel agent runs` is gone. Nothing read it — no endpoint, no agent, no
//     config — so it was a slider that decided nothing.
//   • The thinking-level chips became EFFORT. They encoded a fixed thinking-token
//     budget, which is not how the current models work; `claude --effort` is the
//     knob that actually exists, and the level picked here is passed to it.
//   • `Fast model` is gone. #190 made it persist, which only moved the problem:
//     the hub makes exactly one kind of Claude call — a knowledge build — so
//     there was no second, cheaper invocation for it to choose the model of.
//
// Everything left is real: what is saved here survives a reload and is read
// back by the hub's knowledge builds when they invoke the CLI.
//
// **How it saves changed in #200.** Each control used to `PUT` the moment it
// was touched, which made this the odd one out among the hub's settings screens
// and left no way to try a combination before committing to it — or to change
// your mind. The controls now edit a draft and the shared `SaveBar` commits it,
// the same idiom the project Settings and Repository forms use. The credential
// half of this screen stays immediate, because each of its mutations is a real
// request whose result is already true (see `state.ts`).
//
// Two full-width cards stacked at the shell's 14 px gap, rather than the
// handoff's 2-up model row with one cell empty. The dropdown keeps its 300 px
// width inside the wider card: the card grows, the control does not.

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import {
  Dropdown,
  GlassCard,
  Icon,
  LoadingState,
  Notice,
  SaveBar,
} from "@/components/ui";
import {
  EFFORT_LEVELS,
  MODELS,
  effortOption,
  modelOption,
  type ClaudeSettings,
} from "./state";

export function ModelsTab({ s }: { s: ClaudeSettings }) {
  if (s.modelsError) {
    return <Notice tone="warn">{s.modelsError}</Notice>;
  }
  if (!s.models || !s.draftModels) {
    return <LoadingState label="Loading model preferences…" />;
  }

  return (
    <div className="flex flex-col gap-[14px]">
      {/* The hub tells us whether these are the user's picks or the workspace
          defaults — the values alone cannot say, and showing a default as
          though it had been chosen is the exact dishonesty this slice removes. */}
      {s.models.usingDefaults && (
        <Notice tone="info">
          Showing the workspace defaults — you have not chosen yet. Pick a model
          or an effort level and save to set your own.
        </Notice>
      )}

      <ModelCard
        ddKey="claude-main-model"
        title="Default model"
        description="Used for planning, test generation and code changes."
        value={s.draftModels.mainModel}
        onChange={s.setMainModel}
        busy={s.savingModels}
        dot={<span className="size-[9px] shrink-0 rounded-full bg-accent-grad" />}
      />

      <EffortCard
        value={s.draftModels.effort}
        onChange={s.setEffort}
        busy={s.savingModels}
      />

      {/* Room so the fixed save bar cannot cover the last card. */}
      <div className="h-24 shrink-0" aria-hidden />

      <SaveBar
        count={s.modelsDirtyCount}
        saving={s.savingModels}
        onDiscard={s.discardModels}
        onSave={s.saveModels}
      />
    </div>
  );
}

/* ── Effort ──────────────────────────────────────────────────────────────── */

function EffortCard({
  value,
  onChange,
  busy,
}: {
  value: string;
  onChange: (next: string) => void;
  busy: boolean;
}) {
  const selected = effortOption(value);

  return (
    <GlassCard radius="panel" className="p-[22px]">
      <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
        Effort
      </div>
      <div className="mt-1 text-[12.5px] text-muted">
        How much reasoning a run spends before it acts.
      </div>

      <div className="mt-[15px] flex flex-wrap gap-2">
        {EFFORT_LEVELS.map((level) => {
          const active = level.id === value;
          return (
            <button
              key={level.id}
              type="button"
              data-surface
              disabled={busy}
              aria-pressed={active}
              onClick={() => onChange(level.id)}
              className={cn(
                "cursor-pointer rounded-control px-[14px] py-[7px] text-[12px] font-bold disabled:cursor-not-allowed",
                active
                  ? "border border-pb bg-pt text-p-on"
                  : "border border-bd bg-inset text-muted",
              )}
            >
              {level.label}
            </button>
          );
        })}
      </div>

      {selected && (
        <div className="mt-[14px] flex items-center gap-[9px] rounded-button border border-bd3 bg-inset px-[15px] py-3">
          <span className="shrink-0 text-ps-text">
            <Icon name="bolt" size={15} strokeWidth={2.2} />
          </span>
          <span className="text-[12.5px] text-txt3">{selected.note}</span>
        </div>
      )}
    </GlassCard>
  );
}

function ModelCard({
  ddKey,
  title,
  description,
  value,
  onChange,
  busy,
  dot,
}: {
  ddKey: string;
  title: string;
  description: string;
  /** The stored model **id**. The label is derived, never stored. */
  value: string;
  onChange: (next: string) => void;
  busy: boolean;
  dot: ReactNode;
}) {
  // A saved preference the hub knows and this build does not still has to
  // render — as its own id, rather than as an empty control.
  const selected = modelOption(value);

  return (
    <GlassCard radius="panel" className="p-[22px]">
      <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
        {title}
      </div>
      <div className="mt-1 text-[12.5px] text-muted">{description}</div>
      <Dropdown
        ddKey={ddKey}
        width={300}
        value={value}
        items={MODELS.map((m) => ({ value: m.id, label: m.label }))}
        onSelect={onChange}
        trigger={({ ref, toggle }) => (
          <button
            ref={ref}
            type="button"
            data-surface
            disabled={busy}
            onClick={toggle}
            className="mt-[15px] flex w-[300px] max-w-full cursor-pointer items-center gap-2.5 rounded-button border border-bd2 bg-card3 px-[14px] py-3 hover:border-pb disabled:cursor-not-allowed"
          >
            {dot}
            <span className="flex-1 text-left text-[13px] font-bold text-txt">
              {selected?.label ?? value}
            </span>
            {selected && (
              <span className="shrink-0 rounded-pill border border-bd2 bg-inset px-2 py-[2px] font-mono text-[10.5px] font-semibold text-muted">
                {selected.ctxWindow} ctx
              </span>
            )}
            <span className="shrink-0 text-faint">
              <Icon name="chevronDown" size={14} strokeWidth={2.4} />
            </span>
          </button>
        )}
      />
    </GlassCard>
  );
}

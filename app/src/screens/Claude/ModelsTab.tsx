// Handoff › 6. Claude Settings › Models — "default model + fast model dropdown
// cards, thinking-level chips (Off/Low/Medium/High) with an explanatory line,
// and a `Parallel agent runs` range (1–8)".
//
// **Two changes, both for the same reason** (#190): this tab's whole problem was
// controls that could not do the thing they named.
//
//   • `Parallel agent runs` is gone. Nothing read it — no endpoint, no agent, no
//     config — so it was a slider that decided nothing.
//   • The thinking-level chips became EFFORT. They encoded a fixed thinking-token
//     budget, which is not how the current models work; `claude --effort` is the
//     knob that actually exists, and the level picked here is passed to it.
//
// Everything left is real. Each control writes through to
// `PUT /me/model-preferences` the moment it is used, survives a reload, and is
// read back by the hub's knowledge builds when they invoke the CLI.

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import {
  Dropdown,
  GlassCard,
  Icon,
  LoadingState,
  Notice,
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
  if (!s.models) {
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
          or an effort level to set your own.
        </Notice>
      )}

      <div className="grid grid-cols-2 gap-[14px]">
        <ModelCard
          ddKey="claude-main-model"
          title="Default model"
          description="Used for planning, test generation and code changes."
          value={s.models.mainModel}
          onChange={s.setMainModel}
          busy={s.savingModels}
          dot={<span className="size-[9px] shrink-0 rounded-full bg-accent-grad" />}
        />
        <ModelCard
          ddKey="claude-fast-model"
          title="Fast model"
          description="Used for classification, summaries and import jobs."
          value={s.models.fastModel}
          onChange={s.setFastModel}
          busy={s.savingModels}
          dot={
            <span className="size-[9px] shrink-0 rounded-full bg-[linear-gradient(135deg,var(--txt3),var(--muted))]" />
          }
        />
      </div>

      <EffortCard
        value={s.models.effort}
        onChange={s.setEffort}
        busy={s.savingModels}
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
    <GlassCard radius="panel" className="p-5">
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
            className="mt-[14px] flex w-full cursor-pointer items-center gap-2.5 rounded-button border border-bd2 bg-card3 px-[14px] py-3 hover:border-pb disabled:cursor-not-allowed"
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

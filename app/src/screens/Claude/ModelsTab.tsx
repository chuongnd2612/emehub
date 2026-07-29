// Handoff › 6. Claude Settings › Models — "default model + fast model dropdown
// cards, thinking-level chips (Off/Low/Medium/High) with an explanatory line,
// and a `Parallel agent runs` range (1–8)".

import type { ReactNode } from "react";
import { Dropdown, GlassCard, Icon, Notice, Range } from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  MODELS,
  THINKING_LEVELS,
  THINKING_NOTES,
  type ClaudeSettings,
} from "./state";

export function ModelsTab({ s }: { s: ClaudeSettings }) {
  return (
    <div className="flex flex-col gap-[14px]">
      {/* No settings endpoint exists (verified against /api/openapi.json), so
          these choices live in the screen and are lost on reload. */}
      <Notice tone="info">
        Preview data. The hub has no model-settings endpoint yet, so these
        choices are not saved.
      </Notice>
      <div className="grid grid-cols-2 gap-[14px]">
        <ModelCard
          ddKey="claude-main-model"
          title="Default model"
          description="Used for planning, test generation and code changes."
          value={s.mainModel}
          onChange={s.setMainModel}
          dot={<span className="size-[9px] shrink-0 rounded-full bg-accent-grad" />}
        />
        <ModelCard
          ddKey="claude-fast-model"
          title="Fast model"
          description="Used for classification, summaries and import jobs."
          value={s.fastModel}
          onChange={s.setFastModel}
          dot={
            <span className="size-[9px] shrink-0 rounded-full bg-[linear-gradient(135deg,var(--txt3),var(--muted))]" />
          }
        />
      </div>

      <GlassCard radius="panel" className="p-[22px]">
        <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
          Thinking level
        </div>
        <div className="mt-1 text-[12.5px] text-muted">
          How much extended reasoning agents spend before they act.
        </div>

        <div className="mt-[15px] flex flex-wrap gap-2">
          {THINKING_LEVELS.map((level, i) => {
            const active = s.thinking === i;
            return (
              <button
                key={level}
                type="button"
                data-surface
                aria-pressed={active}
                onClick={() => s.setThinking(i)}
                className={cn(
                  "cursor-pointer rounded-control px-[14px] py-[7px] text-[12px] font-bold",
                  active
                    ? "border border-pb bg-pt text-p-on"
                    : "border border-bd bg-inset text-muted",
                )}
              >
                {level}
              </button>
            );
          })}
        </div>

        <div className="mt-[14px] flex items-center gap-[9px] rounded-button border border-bd3 bg-inset px-[15px] py-3">
          <span className="shrink-0 text-ps-text">
            <Icon name="bolt" size={15} strokeWidth={2.2} />
          </span>
          <span className="text-[12.5px] text-txt3">
            {THINKING_NOTES[s.thinking]}
          </span>
        </div>

        <div className="my-5 h-px bg-bd3" />

        <div className="flex items-center gap-[18px]">
          <div className="flex-1">
            <div className="text-[13.5px] font-bold text-txt">
              Parallel agent runs
            </div>
            <div className="mt-[3px] text-[12px] text-muted">
              Maximum concurrent executions across Q‑Agent and D‑Agent.
            </div>
          </div>
          <Range
            className="w-[220px]"
            min={1}
            max={8}
            step={1}
            value={s.parallel}
            onChange={s.setParallel}
            aria-label="Parallel agent runs"
          />
          <span className="w-[22px] text-right font-mono text-[17px] font-semibold text-txt">
            {s.parallel}
          </span>
        </div>
      </GlassCard>
    </div>
  );
}

function ModelCard({
  ddKey,
  title,
  description,
  value,
  onChange,
  dot,
}: {
  ddKey: string;
  title: string;
  description: string;
  value: string;
  onChange: (next: string) => void;
  dot: ReactNode;
}) {
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
        items={MODELS.map((m) => ({ value: m, label: m }))}
        onSelect={onChange}
        trigger={({ ref, toggle }) => (
          <button
            ref={ref}
            type="button"
            data-surface
            onClick={toggle}
            className="mt-[14px] flex w-full cursor-pointer items-center gap-2.5 rounded-button border border-bd2 bg-card3 px-[14px] py-3 hover:border-pb"
          >
            {dot}
            <span className="flex-1 text-left text-[13px] font-bold text-txt">
              {value}
            </span>
            <span className="shrink-0 text-faint">
              <Icon name="chevronDown" size={14} strokeWidth={2.4} />
            </span>
          </button>
        )}
      />
    </GlassCard>
  );
}

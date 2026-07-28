// Handoff § 2. Overview — activity feed.
//
// "glass list; each row: kind chip (Q-Agent purple, D-Agent cyan, import/kb
// neutral, warn amber), text with a mono accent reference (`SUR-1428`), actor,
// relative time."

import { GlassCard, Icon, type IconName } from "@/components/ui";
import type { ActivityEvent, ActivityKind } from "@/data";

/** Kind chip tint + the colour of the row's mono reference. */
const KIND: Record<ActivityKind, { chip: string; ref: string }> = {
  q: { chip: "bg-qagent-tint text-qagent", ref: "text-qagent" },
  d: { chip: "bg-dagent-tint text-dagent", ref: "text-dagent" },
  sync: { chip: "bg-card3 border border-bd text-txt4", ref: "text-ps-text" },
  kb: { chip: "bg-card3 border border-bd text-txt4", ref: "text-ps-text" },
  key: { chip: "bg-card3 border border-bd text-txt4", ref: "text-ps-text" },
  warn: { chip: "bg-warn-tint text-warn", ref: "text-warn" },
};

export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <GlassCard radius="panel" className="flex flex-col p-5">
      <div className="mb-[6px] flex items-center gap-[10px]">
        <span className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
          Recent activity
        </span>
        <span className="ml-auto text-[11.5px] font-semibold text-ps-text">
          Live feed
        </span>
        <span className="size-[7px] animate-pulse-dot rounded-full bg-ok" />
      </div>

      {events.map((a) => {
        const kind = KIND[a.kind];
        return (
          <div
            key={`${a.ref}-${a.when}`}
            className="flex items-start gap-3 border-b border-bd3 py-[13px] last:border-b-0"
          >
            <span
              className={`flex size-7 shrink-0 items-center justify-center rounded-[9px] ${kind.chip}`}
            >
              <Icon name={a.icon as IconName} size={14} strokeWidth={2.2} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] leading-[1.45] font-semibold text-txt2">
                {a.text}
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span
                  className={`font-mono text-[10.5px] font-semibold ${kind.ref}`}
                >
                  {a.ref}
                </span>
                <span className="size-[3px] rounded-full bg-label" />
                <span className="text-[11px] text-label">{a.by}</span>
              </div>
            </div>
            <span className="pt-[2px] text-[11px] whitespace-nowrap text-label">
              {a.when}
            </span>
          </div>
        );
      })}
    </GlassCard>
  );
}

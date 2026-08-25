// Handoff § 2. Overview — greeting row.
//
// "Good morning, <name>" 28px/900 + a one-line status; right-aligned quick
// actions as ghost chips with icons.
//
// The prototype's copy was "Good morning, Emre" and "Two agents online, 6
// projects connected" — a name that is not the signed-in user's and a count that
// was not counted. The name now comes from `/auth/me` through the auth store and
// the numbers from the same real counts the tiles use, so the line either says
// something true or says nothing.

import type { ReactNode } from "react";

import { Icon, Spinner, type IconName } from "@/components/ui";
import { useAuth } from "@/store/auth";
import { useUi } from "@/store/ui";

/** Greeting by local time — the prototype only ever said "morning". */
const greeting = (): string => {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
};

interface QuickAction {
  label: string;
  /** Replaces the icon while an async action is in flight. */
  glyph?: ReactNode;
  icon: IconName;
  run: () => void;
}

export interface GreetingRowProps {
  /** True while an import raised from here is running — Handoff § 5. */
  importing: boolean;
  /** Opens the Import dialog. */
  onImport: () => void;
  /** Real counts for the status line. `null` while they are still loading. */
  projectCount: number | null;
  connectionCount: number | null;
}

export function GreetingRow({
  importing,
  onImport,
  projectCount,
  connectionCount,
}: GreetingRowProps) {
  const setModal = useUi((s) => s.setModal);
  const user = useAuth((s) => s.user);
  const name = user?.firstName?.trim();

  const actions: QuickAction[] = [
    {
      // Handoff › Async behaviours: the label becomes `Importing…` with the
      // icon spinning while the 1500 ms pull is in flight.
      label: importing ? "Importing…" : "Import tickets",
      glyph: importing ? <Spinner size={15} speed="run" /> : undefined,
      icon: "download",
      run: onImport,
    },
    { label: "Invite member", icon: "users", run: () => setModal("invite") },
    { label: "New project", icon: "plus", run: () => setModal("project") },
  ];

  return (
    <div className="flex flex-wrap items-end gap-4 px-[2px] pt-[2px]">
      <div>
        <h1 className="m-0 text-[28px] leading-none font-black tracking-[-.035em] text-txt">
          {greeting()}
          {name ? `, ${name}` : ""}
        </h1>
        {/* Rendered only once the counts are in: a status line that reads
            "0 projects" while loading is a false statement, not a placeholder. */}
        {projectCount !== null && connectionCount !== null && (
          <p className="mt-[5px] mb-0 text-[13.5px] text-muted">
            {projectCount} {projectCount === 1 ? "project" : "projects"} and{" "}
            {connectionCount}{" "}
            {connectionCount === 1 ? "connection" : "connections"} configured.
          </p>
        )}
      </div>

      <div className="ml-auto flex flex-wrap gap-2">
        {actions.map((a) => (
          <button
            key={a.label}
            type="button"
            data-surface
            onClick={a.run}
            className="flex cursor-pointer items-center gap-2 rounded-[12px] border border-bd2 bg-card2 px-[14px] py-[10px] text-[12.5px] font-semibold text-txt3 transition-[background-color,border-color,transform] duration-200 hover:-translate-y-[2px] hover:border-pb hover:bg-bd"
          >
            <span className="flex text-ps-text">
              {a.glyph ?? <Icon name={a.icon} size={15} strokeWidth={2.2} />}
            </span>
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}

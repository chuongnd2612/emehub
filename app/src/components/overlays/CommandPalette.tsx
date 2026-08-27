// Handoff § Overlays › "Command palette (⌘K / Ctrl+K, or the header search):
// scrim rgba(6,6,10,.62) + blur(6px), panel var(--pop) at 12vh, input row +
// grouped results (pages, projects, actions), Esc closes."
//
// Built on `cmdk` — it owns filtering, keyboard traversal and the selected
// item; we own the chrome. Portalled to document.body (CLAUDE.md).

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";

import { Icon, type IconName } from "@/components/ui";
import { getProjects, getTickets, type Project, type Ticket } from "@/data";
import { useEscape } from "@/hooks/useAnchoredPosition";
import { cn } from "@/lib/cn";
import { ROUTE_HEADER } from "@/components/shell/nav";
import { projectPath } from "@/screens/ProjectDetail/shared";
import { useUi, type ModalKey } from "@/store/ui";

interface ActionEntry {
  label: string;
  icon: IconName;
  to: string;
  modal: ModalKey;
}

/** The Overview quick actions, reachable from anywhere. Copy is final. */
const ACTIONS: ActionEntry[] = [
  { label: "Import tickets", icon: "download", to: "/app/tickets", modal: "import" },
  { label: "Invite member", icon: "users", to: "/app/users", modal: "invite" },
  { label: "New project", icon: "plus", to: "/app/projects", modal: "project" },
];

const PAGES = Object.entries(ROUTE_HEADER).map(([to, meta]) => ({
  to,
  label: meta.title,
}));

const ROW_CLASS = cn(
  "flex w-full cursor-pointer items-center gap-3 rounded-[11px] px-3 py-[11px]",
  "text-[13.5px] font-semibold text-txt2 transition-colors duration-150",
  "data-[selected=true]:bg-bd3",
);

const KIND_CLASS = "shrink-0 text-[10.5px] font-bold tracking-[.08em] text-label";

export function CommandPalette() {
  const navigate = useNavigate();
  const open = useUi((s) => s.paletteOpen);
  const query = useUi((s) => s.paletteQuery);
  const setPaletteOpen = useUi((s) => s.setPaletteOpen);
  const setPaletteQuery = useUi((s) => s.setPaletteQuery);
  const setModal = useUi((s) => s.setModal);

  const [projects, setProjects] = useState<Project[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);

  useEffect(() => {
    if (!open) return;
    let live = true;
    void Promise.all([
      getProjects(),
      Promise.all([getTickets("ado"), getTickets("jira"), getTickets("gh")]),
    ]).then(([p, t]) => {
      if (!live) return;
      setProjects(p);
      setTickets(t.flat());
    });
    return () => {
      live = false;
    };
  }, [open]);

  useEscape(open, () => setPaletteOpen(false));

  const hasQuery = query.trim().length > 0;

  const go = useMemo(
    () => (to: string, modal: ModalKey = null) => {
      setPaletteOpen(false);
      navigate(to);
      if (modal) setModal(modal);
    },
    [navigate, setModal, setPaletteOpen],
  );

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[1100] flex items-start justify-center pt-[12vh]"
      role="presentation"
    >
      {/* Scrim — rgba(6,6,10,.62) + blur(6px). Not a token: it is deliberately
          identical in both modes (it covers the whole viewport). */}
      <div
        className="fixed inset-0 animate-fade-in bg-[rgba(6,6,10,.62)] backdrop-blur-[6px]"
        onClick={() => setPaletteOpen(false)}
      />

      <Command
        label="Command palette"
        loop
        className={cn(
          "relative w-[620px] max-w-[92vw] animate-scale-in overflow-hidden",
          "rounded-[18px] border border-bd2 bg-pop shadow-dialog",
        )}
      >
        <div className="flex items-center gap-3 border-b border-bd px-[18px] py-4">
          <span className="flex shrink-0 text-ps-text">
            <Icon name="search" size={17} strokeWidth={2.2} />
          </span>
          <Command.Input
            autoFocus
            value={query}
            onValueChange={setPaletteQuery}
            placeholder="Jump to a page, project, or ticket…"
            className={cn(
              "min-w-0 flex-1 bg-transparent text-[15px] font-medium text-txt outline-none",
              "placeholder:text-faint",
            )}
          />
          <span className="shrink-0 rounded-[7px] border border-bd2 bg-bd3 px-[7px] py-[3px] font-mono text-[10px] font-semibold text-muted">
            ESC
          </span>
        </div>

        <Command.List
          className={cn(
            "max-h-[340px] overflow-y-auto p-2",
            "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1.5",
            "[&_[cmdk-group-heading]]:text-[9.5px] [&_[cmdk-group-heading]]:font-bold",
            "[&_[cmdk-group-heading]]:tracking-[.12em] [&_[cmdk-group-heading]]:text-label",
          )}
        >
          <Command.Empty className="px-4 py-[34px] text-center text-[13px] text-faint">
            No matches. Try “tickets” or “keys”.
          </Command.Empty>

          <Command.Group heading="PAGES">
            {PAGES.map((p) => (
              <Command.Item
                key={p.to}
                value={`page ${p.label}`}
                onSelect={() => go(p.to)}
                className={ROW_CLASS}
              >
                <span className="flex w-[18px] shrink-0 justify-center text-ps-text">
                  <Icon name="grid" size={15} strokeWidth={2.2} />
                </span>
                <span className="min-w-0 flex-1 truncate text-left">
                  {p.label}
                </span>
                <span className={KIND_CLASS}>PAGE</span>
              </Command.Item>
            ))}
          </Command.Group>

          {hasQuery && (
            <Command.Group heading="PROJECTS">
              {projects.map((p) => (
                <Command.Item
                  key={p.id}
                  value={`project ${p.name} ${p.repo}`}
                  onSelect={() => go(projectPath(p.guid || p.id))}
                  className={ROW_CLASS}
                >
                  <span className="flex w-[18px] shrink-0 justify-center text-ps-text">
                    <Icon name="folder" size={15} strokeWidth={2.2} />
                  </span>
                  <span className="min-w-0 flex-1 truncate text-left">
                    {p.name}
                  </span>
                  <span className={KIND_CLASS}>PROJECT</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {hasQuery && (
            <Command.Group heading="TICKETS">
              {tickets.map((t) => (
                <Command.Item
                  key={t.id}
                  value={`ticket ${t.id} ${t.title}`}
                  onSelect={() => go("/app/tickets")}
                  className={ROW_CLASS}
                >
                  <span className="flex w-[18px] shrink-0 justify-center text-ps-text">
                    <Icon name="ticket" size={15} strokeWidth={2.2} />
                  </span>
                  <span className="min-w-0 flex-1 truncate text-left">
                    {t.id} — {t.title}
                  </span>
                  <span className={KIND_CLASS}>TICKET</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}

          <Command.Group heading="ACTIONS">
            {ACTIONS.map((a) => (
              <Command.Item
                key={a.label}
                value={`action ${a.label}`}
                onSelect={() => go(a.to, a.modal)}
                className={ROW_CLASS}
              >
                <span className="flex w-[18px] shrink-0 justify-center text-ps-text">
                  <Icon name={a.icon} size={15} strokeWidth={2.2} />
                </span>
                <span className="min-w-0 flex-1 truncate text-left">
                  {a.label}
                </span>
                <span className={KIND_CLASS}>ACTION</span>
              </Command.Item>
            ))}
          </Command.Group>
        </Command.List>
      </Command>
    </div>,
    document.body,
  );
}

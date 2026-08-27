// Project › Tickets (#221, handoff §3, ADR 0011 §1/§3) — the sixth tab, and a
// real view rather than a link out to a workspace-wide list.
//
// This file does exactly two things: it **derives the ticket source** from the
// project, and it renders `TicketsView` scoped by `projectId`. The list itself is
// the same component the Unassigned bucket uses, so there is one ticket table in
// the app rather than one per container.
//
// ## Provider is derived, and the failure cases are not collapsed
//
// `resolveTicketSource(project)` (`data/ticketSource.ts`) answers with one of
// four states, and each gets its own screen here. That is the whole point: the
// old screen offered a provider switch, so the user could put the list on a
// provider that had nothing to do with the project they were in. Removing the
// switch only helps if the derivation is honest about not knowing — a fabricated
// provider is the same defect with fewer clicks.
//
//   resolved     the list, sourced from that connection
//   none         no work-item connection is configured — an empty state whose
//                CTA opens the Settings tab, which is where the binding lives
//   unresolved   the project names a connection this caller cannot see; the id
//                is shown, because that is the actionable part
//   unavailable  the config or the connection list could not be read — an error
//                state with Retry, never "not connected"
//
// ## The count comes from the one counting path
//
// The tab's badge is `ticketCountFor(getTicketCounts(), rowId)` — the same
// function the sidebar tree (#220) and the Overview comparison table (#218) read
// (handoff §3: "no screen may compute a count its own way"). It is rendered by
// `ProjectDetail/index.tsx` on the tab button; this file does not count anything.
// The pager's total is a different figure on purpose: it is the size of the
// *filtered* set, which is the question the pager is answering.

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, GlassCard, Icon } from "@/components/ui";
import {
  PROVIDERS,
  resolveTicketSource,
  type Project,
  type TicketSource,
} from "@/data";
import { TicketsView } from "@/screens/Tickets/TicketsView";

import { projectTicketPath } from "./shared";

export interface TicketsTabProps {
  project: Project;
  /** Opens the Settings tab, where the work-item connection is bound. */
  onOpenSettings: () => void;
}

export function TicketsTab({ project, onOpenSettings }: TicketsTabProps) {
  const [source, setSource] = useState<TicketSource | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    void resolveTicketSource(project)
      .then((resolved) => {
        if (live) setSource(resolved);
      })
      // `resolveTicketSource` already answers `unavailable` rather than
      // throwing; this is the belt-and-braces case, and it says the same thing.
      .catch(() => {
        if (live) setSource({ state: "unavailable" });
      });
    return () => {
      live = false;
    };
  }, [project, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const configure = (
    <button
      type="button"
      data-surface
      onClick={onOpenSettings}
      className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-button border-none bg-accent-grad px-[18px] text-[12.5px] font-bold text-white shadow-primary transition-transform duration-200 hover:-translate-y-px"
    >
      <Icon name="plug" size={14} strokeWidth={2.3} />
      Configure the ticket source
    </button>
  );

  if (source === null) {
    return (
      <GlassCard className="rounded-[20px] p-0">
        {/* The geometry of what is coming, so the tab does not jump. */}
        <div className="flex flex-col gap-2.5 p-5" aria-hidden>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <span key={i} className="skeleton h-[34px] w-full rounded-[10px]" />
          ))}
        </div>
      </GlassCard>
    );
  }

  if (source.state === "unavailable") {
    return (
      <GlassCard className="rounded-[20px]">
        <ErrorState
          title="Could not read this project's ticket source"
          detail="The project's configuration or the connection list did not load, so EmeHub cannot say which provider these work items come from. It will not guess one."
          onRetry={retry}
        />
      </GlassCard>
    );
  }

  if (source.state === "none") {
    return (
      <GlassCard className="rounded-[20px]">
        <EmptyState
          icon="plug"
          title="No ticket source is bound to this project"
          body="Work items reach EmeHub through the connection configured on the project, and this one has none. Bind an Azure DevOps or Jira connection and the mirror fills on the next import."
          action={configure}
        />
      </GlassCard>
    );
  }

  if (source.state === "unresolved") {
    return (
      <GlassCard className="rounded-[20px]">
        <EmptyState
          icon="alert"
          title="This project's ticket source cannot be resolved"
          body={`The project is bound to connection ${source.connectionId}, which EmeHub cannot see — it may have been removed, or it belongs to another member. Rebind the project to a connection you own; the provider is never guessed.`}
          action={configure}
        />
      </GlassCard>
    );
  }

  return (
    <TicketsView
      scope={{
        kind: "project",
        projectId: project.rowId,
        provider: source.provider,
        sourceLabel: source.label,
      }}
      ticketHref={(ticket) =>
        projectTicketPath(
          project.guid || project.id,
          ticket.id,
          // The ROW's own provider, not the project's: the row is the authority
          // on where it came from, and `(providerKind, externalId)` is what
          // identifies it on the far side. Falling back to the project's source
          // keeps the link disambiguated for a row stored without a kind.
          ticket.provider ?? source.provider,
        )
      }
      empty={{
        title: `Nothing mirrored from ${PROVIDERS[source.provider].name} yet`,
        body: "EmeHub keeps a read-only copy of this project's work items so every agent reads the same backlog. Run an import to pull the first batch.",
      }}
      footnote={`Read-only mirror of ${source.label}. Edit work items in the provider — the next import reflects the change.`}
    />
  );
}

// The Unassigned bucket — `/app/unassigned/tickets` (#221, ADR 0011 §4).
//
// Work items whose `project_id` is NULL: rows the #217 migration could not
// backfill from the ticket's connection, plus anything that arrives without a
// project stamp in future. Under containment they belong to no container, so
// without this screen they would **appear nowhere** — which is not a display bug
// but a silent disappearance of data, and the reason the handoff insists the
// bucket is explicit, visible, "never hidden, never guessed at".
//
// It has a workspace-level address rather than a fake project id because it is
// genuinely not inside a project (#219, `router.tsx`), and a sidebar row of its
// own for the same reason: the tree lists projects, and the bucket is not one.
// The row is rendered unconditionally — an empty bucket still has an address, and
// hiding it would mean a user could not confirm that nothing is unattributed.
//
// ## Read-only, deliberately
//
// There is no assign-to-project control and there will not be one until the
// decision changes. Tickets are billed throughout the hub as a read-only mirror
// of Azure DevOps and Jira, and the project a ticket belongs to is derived from
// the connection it arrived through; a UI that re-pointed one mirrored row would
// be the first hub-side write to a mirror's own shape, and the next sync would
// either overwrite it or have to learn to respect it. The escape hatch is binding
// the connection to a project and re-syncing, not a write from here.
//
// So this screen offers search, the table and the pager, and deliberately not:
//
//   • an Import button — an import pulls into the project its connection is
//     bound to, never into the bucket;
//   • the clause builder — `POST /tickets/search` has no `unassigned` parameter,
//     and adding one is a contract change this slice does not make;
//   • a source chip — these rows may have arrived through more than one
//     connection, so there is no single source to name. The filter pills appear
//     only when every row in scope agrees on a provider, which is the one case
//     where provider vocabulary is not a guess.

import { GlassCard } from "@/components/ui";
import { TicketsView } from "@/screens/Tickets/TicketsView";
import { unassignedTicketPath } from "@/screens/ProjectDetail/shared";

export default function UnassignedTicketsScreen() {
  return (
    <div className="flex animate-fade-in-up flex-col gap-[14px]">
      <GlassCard className="rounded-[20px] p-5">
        <h2 className="m-0 text-[15px] font-black tracking-[-.02em] text-txt">
          Work items that belong to no project
        </h2>
        <p className="m-0 mt-1.5 max-w-[760px] text-[12.5px] leading-[1.55] text-muted">
          These rows arrived before EmeHub stamped a project on every work item,
          or through a connection that is not bound to one. They are listed here
          so nothing is invisible. Bind the connection to a project and re-import
          to move them — the mirror is read-only, so nothing reassigns them from
          this screen.
        </p>
      </GlassCard>

      <TicketsView
        scope={{ kind: "unassigned" }}
        ticketHref={(ticket) => unassignedTicketPath(ticket.id, ticket.provider)}
        empty={{
          title: "Every work item belongs to a project",
          body: "Nothing in the mirror is unassigned. This bucket fills only when a sync stores a work item EmeHub cannot attribute to a project.",
        }}
        footnote="Read-only mirror. A work item leaves this bucket when its connection is bound to a project and the next import runs."
      />
    </div>
  );
}

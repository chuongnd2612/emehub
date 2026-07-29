// Handoff § 4. Tickets › Table — glass container, columns
// `110px | 2.4fr | 1fr | 120px | 120px | 110px | 110px` with gap 12, a
// 9.5px/700/.11em header row, 14px/20px rows on a 1px var(--bd3) divider,
// var(--card3) on hover and a "read-only mirror" toast on click.
//
// ## Two of the handoff's seven columns have no source
//
// AGENT — the hub does not assign an agent to a work item; there is no such
// field on `Ticket`. IMPORT — every stored row is imported by definition (it
// exists because a sync put it there), so a per-row import status would always
// read "Imported".
//
// They are replaced by two columns the hub genuinely knows: TYPE (the provider
// work-item type) and SYNCED (when the mirror last saw the row). Widths and the
// column count are unchanged.

import type { Ticket } from "@/data";
import {
  Pill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  statusTone,
} from "@/components/ui";

/** The one inline style the rules allow: a computed grid template. */
const COLUMNS = "110px minmax(0,2.4fr) minmax(0,1fr) 120px 120px 110px 110px";

const HEADINGS = [
  "ID",
  "WORK ITEM",
  "PROJECT",
  "STATUS",
  "TYPE",
  "SYNCED",
  "ASSIGNEE",
];

export interface TicketsTableProps {
  tickets: Ticket[];
  /** Display name of the active provider — used by the empty state. */
  providerName: string;
  onRowClick: (ticket: Ticket) => void;
}

export function TicketsTable({
  tickets,
  providerName,
  onRowClick,
}: TicketsTableProps) {
  return (
    <Table>
      <TableRow columns={COLUMNS} header>
        {HEADINGS.map((h) => (
          <TableCell key={h}>{h}</TableCell>
        ))}
      </TableRow>

      {tickets.map((t) => (
        <TableRow
          key={`${t.provider ?? ""}-${t.id}`}
          columns={COLUMNS}
          interactive
          onClick={() => onRowClick(t)}
        >
          <TableCell mono className="text-ps-text">
            {t.id}
          </TableCell>
          <TableCell className="text-[13px] font-semibold text-txt2">
            {t.title}
          </TableCell>
          <TableCell className="text-[12px] text-txt4">
            {t.project || "—"}
          </TableCell>
          <TableCell>
            {t.status ? (
              <Pill tone={statusTone(t.status)}>{t.status}</Pill>
            ) : (
              <span className="text-[12px] text-faint">—</span>
            )}
          </TableCell>
          <TableCell className="text-[12px] text-txt4">
            {t.type || "—"}
          </TableCell>
          <TableCell className="text-[11.5px] text-muted">{t.synced}</TableCell>
          <TableCell className="text-[12px] text-muted">
            {t.owner || "Unassigned"}
          </TableCell>
        </TableRow>
      ))}

      {tickets.length === 0 && (
        <TableEmpty
          icon="search"
          message="No work items match these filters"
          action={
            <p className="m-0 text-[12.5px] text-muted">
              Clear a filter, or import a wider scope from {providerName}.
            </p>
          }
        />
      )}
    </Table>
  );
}

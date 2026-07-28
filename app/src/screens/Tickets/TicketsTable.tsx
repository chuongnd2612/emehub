// Handoff § 4. Tickets › Table — glass container, columns
// `110px | 2.4fr | 1fr | 120px | 120px | 110px | 110px` with gap 12, a
// 9.5px/700/.11em header row (ID · WORK ITEM · PROJECT · STATUS · AGENT ·
// IMPORT · OWNER), 14px/20px rows on a 1px var(--bd3) divider, var(--card3) on
// hover and a "read-only mirror" toast on click.

import type { AgentKey, Ticket } from "@/data";
import {
  Pill,
  StatusPill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  type StatusName,
} from "@/components/ui";

/** The one inline style the rules allow: a computed grid template. */
const COLUMNS = "110px minmax(0,2.4fr) minmax(0,1fr) 120px 120px 110px 110px";

const HEADINGS = [
  "ID",
  "WORK ITEM",
  "PROJECT",
  "STATUS",
  "AGENT",
  "IMPORT",
  "OWNER",
];

const AGENT_NAME: Record<AgentKey, string> = {
  q: "Q-Agent",
  d: "D-Agent",
};

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
          key={t.id}
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
          <TableCell className="text-[12px] text-txt4">{t.project}</TableCell>
          <TableCell>
            <StatusPill status={t.status as StatusName} />
          </TableCell>
          <TableCell>
            {t.agent ? (
              <Pill tone={t.agent === "q" ? "qagent" : "dagent"}>
                {AGENT_NAME[t.agent]}
              </Pill>
            ) : (
              <Pill tone="neutral">Unassigned</Pill>
            )}
          </TableCell>
          <TableCell>
            <StatusPill status={t.sync as StatusName} />
          </TableCell>
          <TableCell className="text-[12px] text-muted">{t.owner}</TableCell>
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

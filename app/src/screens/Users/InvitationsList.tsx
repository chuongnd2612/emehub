// Handoff § 8 › Invitations — "rows with dashed envelope tile, email, role
// chip, sent/by, `Resend` + destructive `Revoke`".
//
// Presentational: the invitation list is owned by the screen so a freshly sent
// invitation lands in it immediately.

import {
  Button,
  Icon,
  Pill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  toast,
} from "@/components/ui";
import type { Invitation } from "@/data";

const COLUMNS = "36px minmax(0,2fr) 110px 120px minmax(0,1fr) 190px";

export interface InvitationsListProps {
  invitations: Invitation[];
  onRevoke: (invitation: Invitation) => void;
  /** Opens the Invite member modal from the empty state. */
  onInvite: () => void;
}

export function InvitationsList({
  invitations,
  onRevoke,
  onInvite,
}: InvitationsListProps) {
  const resend = (inv: Invitation) =>
    toast("Invitation resent", `${inv.email} will receive a fresh link`, "ok");

  const revoke = (inv: Invitation) => {
    onRevoke(inv);
    toast(
      "Invitation revoked",
      `${inv.email} can no longer join this workspace`,
      "warn",
    );
  };

  return (
    <Table>
      {invitations.length === 0 ? (
        <TableEmpty
          icon="mail"
          message="No pending invitations"
          action={
            <Button variant="primary" onClick={onInvite}>
              Invite member
            </Button>
          }
        />
      ) : (
        invitations.map((inv) => (
          <TableRow key={inv.email} columns={COLUMNS}>
            <TableCell>
              <span className="flex size-[34px] shrink-0 items-center justify-center rounded-glyph border border-dashed border-bd2 bg-bd3 text-muted">
                <Icon name="mail" size={15} strokeWidth={2.2} />
              </span>
            </TableCell>
            <TableCell className="text-[13px] font-semibold text-txt2">
              {inv.email}
            </TableCell>
            <TableCell align="start">
              <Pill tone="neutral" size="sm">
                {inv.role}
              </Pill>
            </TableCell>
            <TableCell className="text-[12px] text-muted">
              sent {inv.sent}
            </TableCell>
            <TableCell className="text-[12px] text-label">
              by {inv.by}
            </TableCell>
            <TableCell align="end" className="gap-2">
              <Button variant="ghost" size="sm" onClick={() => resend(inv)}>
                Resend
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => revoke(inv)}
              >
                Revoke
              </Button>
            </TableCell>
          </TableRow>
        ))
      )}
    </Table>
  );
}

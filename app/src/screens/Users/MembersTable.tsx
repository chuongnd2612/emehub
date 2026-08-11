// Handoff § 8 › Members — the credential cell is a 7px dot + label; the role
// cell is a badge, and a changeable role opens a dropdown.
//
// Live against `GET /auth/users` and `PATCH /auth/users/{id}`.
//
// Three departures from the prototype, all forced by what the hub actually
// stores (see `data/people.ts` for the reasoning):
//   • The role picker offers Admin and Member only. Owner and Viewer are design
//     vocabulary with no storage behind them, and PATCHing either 400s.
//   • The CLAUDE CREDENTIAL column reads "Not assigned" on every row: nothing
//     on the hub maps a user to a credential. It stays because the column is in
//     the design and the mapping is coming; it does not fabricate an answer.
//   • A DEVICES column is added, because `AdminUserOut.sessionCount` is real.
//
// The endpoint is admin-only. A member gets a 403, which surfaces as its own
// error state rather than an empty table.

import { useCallback, useEffect, useState } from "react";

import {
  Dropdown,
  ErrorState,
  Glyph,
  Icon,
  LoadingState,
  Pill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  toast,
  type PillTone,
} from "@/components/ui";
import {
  ASSIGNABLE_ROLES,
  getMembers,
  updateMember,
  type Member,
  type MemberPatch,
  type RoleName,
} from "@/data";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useAuth } from "@/store/auth";
import { RenameMemberModal } from "./RenameMemberModal";

const COLUMNS =
  "36px minmax(0,1.05fr) minmax(0,1.3fr) 150px 110px 90px 130px 34px";

/** The row action menu. `rename` opens a modal; the rest are direct PATCHes. */
type RowAction = "rename" | "deactivate" | "reactivate";

const ROLE_TONE: Record<RoleName, PillTone> = {
  Owner: "accent",
  Admin: "qagent",
  Member: "dagent",
  Viewer: "neutral",
};

export function MembersTable() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [renaming, setRenaming] = useState<Member | null>(null);

  const me = useAuth((s) => s.user);
  const refreshUser = useAuth((s) => s.refreshUser);

  const load = useCallback(async () => {
    setError(null);
    setForbidden(false);
    try {
      setMembers(await getMembers());
    } catch (err) {
      setMembers(null);
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
        return;
      }
      setError(
        err instanceof ApiError ? err.message : "The hub did not respond.",
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const replaceRow = (updated: Member) =>
    setMembers(
      (prev) => prev?.map((m) => (m.id === updated.id ? updated : m)) ?? null,
    );

  /**
   * One PATCH, one row. The updated member goes in unmodified — `updateMember`
   * resolves `sessionCount` itself, because only it knows that deactivating
   * revoked them.
   *
   * Every failure here is the hub declining for a reason worth reading — most
   * often the zero-active-admins guard — so `ApiError.message` is surfaced
   * verbatim rather than replaced with a generic apology.
   */
  const patchMember = async (
    member: Member,
    patch: MemberPatch,
    ok: string,
    failed: string,
  ) => {
    setBusyId(member.id);
    try {
      replaceRow(await updateMember(member, patch));
      toast(ok);
      // Demoting or deactivating YOURSELF changes what you may do next — the
      // hub allows both while an admin remains, so resync the principal.
      if (me?.id === member.id) void refreshUser();
    } catch (err) {
      toast(
        failed,
        "warn",
        err instanceof ApiError ? err.message : "The hub did not respond.",
      );
    } finally {
      setBusyId(null);
    }
  };

  const pickRole = (member: Member, role: RoleName) => {
    if (role === member.role) return;
    void patchMember(
      member,
      { role },
      "Role updated",
      "Could not change that role",
    );
  };

  const runAction = (member: Member, action: RowAction) => {
    if (action === "rename") {
      setRenaming(member);
      return;
    }
    const isActive = action === "reactivate";
    void patchMember(
      member,
      { isActive },
      isActive ? "Member reactivated" : "Member deactivated",
      isActive
        ? "Could not reactivate that member"
        : "Could not deactivate that member",
    );
  };

  if (forbidden) {
    return (
      <Table>
        <ErrorState
          title="You need admin access to see members"
          detail="Only workspace admins can list accounts. Ask an admin to change your role, or open Authentication to manage your own session."
        />
      </Table>
    );
  }

  if (error) {
    return (
      <Table>
        <ErrorState
          title="Could not load workspace members"
          detail={error}
          onRetry={() => void load()}
        />
      </Table>
    );
  }

  if (members === null) {
    return (
      <Table>
        <LoadingState label="Loading members…" />
      </Table>
    );
  }

  return (
    <>
      <Table>
        <TableRow columns={COLUMNS} header>
          <span />
          <span>MEMBER</span>
          <span>EMAIL</span>
          <span>CLAUDE CREDENTIAL</span>
          <span>LAST ACTIVE</span>
          <span>DEVICES</span>
          <span className="text-right">ROLE</span>
          <span />
        </TableRow>

        {members.length === 0 ? (
          <TableEmpty icon="users" message="No members in this workspace yet" />
        ) : (
          members.map((m) => (
            <TableRow
              key={m.id}
              columns={COLUMNS}
              className={cn(!m.isActive && "opacity-55")}
            >
              <TableCell>
                <Glyph size={34} fill="accent" label={m.initials} />
              </TableCell>
              <TableCell className="text-[13.5px] font-bold text-txt2">
                <span className="truncate">{m.name}</span>
                {!m.isActive && (
                  <Pill tone="neutral" size="sm">
                    Deactivated
                  </Pill>
                )}
                {me?.id === m.id && (
                  <Pill tone="accent" size="sm">
                    You
                  </Pill>
                )}
              </TableCell>
              <TableCell className="text-[12.5px] text-muted">
                {m.email}
              </TableCell>
              <TableCell>
                {/* STUB (no endpoint yet): no user → Claude credential mapping. */}
                <span className="size-[7px] shrink-0 rounded-full bg-bd2" />
                <span className="truncate text-[12px] text-label">
                  Not assigned
                </span>
              </TableCell>
              <TableCell className="text-[12px] text-label">
                {m.lastActive}
              </TableCell>
              <TableCell mono className="text-muted">
                {m.sessionCount}
              </TableCell>
              <TableCell align="end">
                <Dropdown<RoleName>
                  ddKey={`role:${m.id}`}
                  width={170}
                  align="end"
                  value={m.role}
                  items={ASSIGNABLE_ROLES.map((r) => ({ value: r, label: r }))}
                  onSelect={(role) => void pickRole(m, role)}
                  trigger={({ ref, toggle }) => (
                    <button
                      ref={ref}
                      type="button"
                      disabled={busyId === m.id}
                      onClick={toggle}
                      className={cn(
                        "flex cursor-pointer items-center gap-[7px] rounded-control-lg",
                        "border border-bd2 bg-card2 px-[11px] py-1.5",
                        "transition-colors duration-200 hover:bg-bd3",
                        "disabled:cursor-not-allowed disabled:opacity-50",
                      )}
                    >
                      <Pill tone={ROLE_TONE[m.role]} size="sm">
                        {m.role}
                      </Pill>
                      <Icon
                        name="chevronDown"
                        size={13}
                        strokeWidth={2.4}
                        className="text-faint"
                      />
                    </button>
                  )}
                />
              </TableCell>

              <TableCell align="end">
                <Dropdown<RowAction>
                  ddKey={`actions:${m.id}`}
                  width={196}
                  align="end"
                  items={[
                    {
                      value: "rename",
                      label: "Rename…",
                      icon: <Icon name="doc" size={13} />,
                    },
                    // One row offers one of these two, never both — the action is
                    // whatever the current state is not.
                    m.isActive
                      ? {
                          value: "deactivate",
                          label: "Deactivate",
                          icon: <Icon name="lock" size={13} />,
                        }
                      : {
                          value: "reactivate",
                          label: "Reactivate",
                          icon: <Icon name="check" size={13} />,
                        },
                  ]}
                  onSelect={(action) => runAction(m, action)}
                  trigger={({ ref, toggle }) => (
                    <button
                      ref={ref}
                      type="button"
                      aria-label={`Actions for ${m.name}`}
                      disabled={busyId === m.id}
                      onClick={toggle}
                      className={cn(
                        "flex size-[26px] cursor-pointer items-center justify-center",
                        "rounded-control text-faint",
                        "transition-colors duration-200 hover:bg-bd3 hover:text-txt2",
                        "disabled:cursor-not-allowed disabled:opacity-50",
                      )}
                    >
                      <Icon name="more" size={15} strokeWidth={2.4} />
                    </button>
                  )}
                />
              </TableCell>
            </TableRow>
          ))
        )}
      </Table>

      <RenameMemberModal
        member={renaming}
        onClose={() => setRenaming(null)}
        onRenamed={replaceRow}
      />
    </>
  );
}

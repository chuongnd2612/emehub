// Handoff § 8 › Members — columns `36px | 1.05fr | 1.3fr | 170px | 110px |
// 130px`, header `MEMBER · EMAIL · CLAUDE CREDENTIAL · LAST ACTIVE · ROLE`.
// The credential cell is a 7px dot + label; the role cell is a badge, and
// non-owners open a role dropdown.

import { useEffect, useState } from "react";
import {
  Dropdown,
  Glyph,
  Icon,
  Pill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  toast,
  type PillTone,
} from "@/components/ui";
import {
  changeRole,
  getMembers,
  getSharedCredentials,
  type Member,
  type RoleName,
  type SharedCredential,
} from "@/data";
import { cn } from "@/lib/cn";

const COLUMNS = "36px minmax(0,1.05fr) minmax(0,1.3fr) 170px 110px 130px";

const ROLES: RoleName[] = ["Owner", "Admin", "Member", "Viewer"];

const ROLE_TONE: Record<RoleName, PillTone> = {
  Owner: "accent",
  Admin: "qagent",
  Member: "dagent",
  Viewer: "neutral",
};

/** Dot + label for the Claude credential cell. Tokens only — no hex. */
function credentialCell(
  member: Member,
  shared: SharedCredential[],
): { dot: string; text: string; label: string } {
  if (member.credential === "personal") {
    return { dot: "bg-dagent", text: "text-cyan-soft", label: "Personal token" };
  }
  if (member.credential === "none") {
    return { dot: "bg-bd2", text: "text-label", label: "Not assigned" };
  }
  const match = shared.find((c) => c.id === member.credentialId);
  return {
    dot: "bg-claude",
    text: "text-txt3",
    label: match ? match.label : "Shared account",
  };
}

export function MembersTable() {
  const [members, setMembers] = useState<Member[]>([]);
  const [shared, setShared] = useState<SharedCredential[]>([]);

  useEffect(() => {
    let live = true;
    void getMembers().then((rows) => live && setMembers(rows));
    void getSharedCredentials().then((rows) => live && setShared(rows));
    return () => {
      live = false;
    };
  }, []);

  const pickRole = (member: Member, role: RoleName) => {
    if (role === member.role) return;
    void changeRole(member.email, role).then(setMembers);
    toast("Role updated", `${member.email} is now a ${role}`, "ok");
  };

  return (
    <Table>
      <TableRow columns={COLUMNS} header>
        <span />
        <span>MEMBER</span>
        <span>EMAIL</span>
        <span>CLAUDE CREDENTIAL</span>
        <span>LAST ACTIVE</span>
        <span className="text-right">ROLE</span>
      </TableRow>

      {members.length === 0 ? (
        <TableEmpty icon="users" message="No members in this workspace yet" />
      ) : (
        members.map((m) => {
          const cred = credentialCell(m, shared);
          const locked = m.role === "Owner";
          return (
            <TableRow key={m.email} columns={COLUMNS}>
              <TableCell>
                <Glyph size={34} fill="accent" label={m.initials} />
              </TableCell>
              <TableCell className="text-[13.5px] font-bold text-txt2">
                {m.name}
              </TableCell>
              <TableCell className="text-[12.5px] text-muted">
                {m.email}
              </TableCell>
              <TableCell>
                <span
                  className={cn("size-[7px] shrink-0 rounded-full", cred.dot)}
                />
                <span className={cn("truncate text-[12px]", cred.text)}>
                  {cred.label}
                </span>
              </TableCell>
              <TableCell className="text-[12px] text-label">
                {m.lastActive}
              </TableCell>
              <TableCell align="end">
                {locked ? (
                  <Pill tone={ROLE_TONE[m.role]} size="sm">
                    {m.role}
                  </Pill>
                ) : (
                  <Dropdown<RoleName>
                    ddKey={`role:${m.email}`}
                    width={170}
                    align="end"
                    value={m.role}
                    items={ROLES.map((r) => ({ value: r, label: r }))}
                    onSelect={(role) => pickRole(m, role)}
                    trigger={({ ref, toggle }) => (
                      <button
                        ref={ref}
                        type="button"
                        onClick={toggle}
                        className={cn(
                          "flex cursor-pointer items-center gap-[7px] rounded-control-lg",
                          "border border-bd2 bg-card2 px-[11px] py-1.5",
                          "transition-colors duration-200 hover:bg-bd3",
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
                )}
              </TableCell>
            </TableRow>
          );
        })
      )}
    </Table>
  );
}

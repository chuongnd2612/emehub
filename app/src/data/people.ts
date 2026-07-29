// People — workspace members, roles and pending invitations.
//
// Members and invitations are real; roles and the invitation LIST are not.
//
//   GET   /auth/users          getMembers
//   PATCH /auth/users/{id}     changeRole
//   POST  /auth/users/invite   invite
//
// ## The role vocabulary is narrower on the wire than in the design
//
// The handoff's Roles grid describes four roles. The hub stores two —
// `USER_ROLES = ("admin", "member")` in `api/app/models/user.py` — and
// `PATCH /auth/users/{id}` 400s on anything else. So `RoleName` keeps all four
// (the Roles grid still renders them from fixtures) but only the two in
// `ASSIGNABLE_ROLES` round-trip, and the member role picker offers only those.
// Owner and Viewer are design vocabulary with no storage behind them; inventing
// a mapping (say, "the first admin is the Owner") would be inventing data.

import { api } from "@/lib/api";
import { INVITATIONS, ROLES } from "./fixtures/people";
import { displayNameFrom, initialsFrom, relativeTime } from "./humanize";
import { after, READ_DELAY_MS } from "./timing";
import type { Invitation, Member, Role, RoleName } from "./types";

/* ── Role mapping ────────────────────────────────────────────────────────── */

/** The roles `PATCH /auth/users/{id}` will actually accept. */
export const ASSIGNABLE_ROLES: RoleName[] = ["Admin", "Member"];

const WIRE_TO_ROLE: Record<string, RoleName> = {
  admin: "Admin",
  member: "Member",
};

const ROLE_TO_WIRE: Partial<Record<RoleName, string>> = {
  Admin: "admin",
  Member: "member",
};

/** Display name for a raw hub role. Unknown roles fall back to "Member". */
export const roleName = (wire: string): RoleName =>
  WIRE_TO_ROLE[(wire ?? "").toLowerCase()] ?? "Member";

/** Inverse. Throws rather than silently sending a role the hub will reject. */
export const roleWire = (role: RoleName): string => {
  const wire = ROLE_TO_WIRE[role];
  if (!wire) {
    throw new Error(`The hub has no "${role}" role — pick Admin or Member.`);
  }
  return wire;
};

/* ── Members ─────────────────────────────────────────────────────────────── */

/** `AdminUserOut` as the hub sends it. */
interface AdminUserWire {
  id: number;
  email: string;
  firstName: string;
  lastName: string;
  role: string;
  isActive: boolean;
  totpEnabled: boolean;
  createdAt: string | null;
  updatedAt: string | null;
  lastActive: string | null;
  sessionCount: number;
}

const toMember = (wire: AdminUserWire): Member => ({
  id: wire.id,
  name: displayNameFrom(wire.firstName, wire.lastName, wire.email),
  email: wire.email,
  role: roleName(wire.role),
  lastActive: relativeTime(wire.lastActive),
  initials: initialsFrom(wire.firstName, wire.lastName, wire.email),
  isActive: wire.isActive,
  sessionCount: wire.sessionCount ?? 0,
  // STUB (no endpoint yet): nothing on the hub maps a user to a Claude
  // credential, so this column reads "Not assigned" for every live row.
  credential: "none",
  credentialId: null,
});

/** `GET /auth/users`. Admin-only — a plain member gets a 403 here. */
export const getMembers = async (): Promise<Member[]> => {
  const rows = await api.get<AdminUserWire[]>("/auth/users");
  return rows.map(toMember);
};

/**
 * `PATCH /auth/users/{id}` — the role change from the Members table.
 *
 * Takes the user **id**, not the email: the hub keys this route on the id and
 * there is no lookup-by-email endpoint. Resolves to the single updated member
 * so the caller can patch one row instead of re-reading the list.
 */
export const changeRole = async (
  userId: number,
  role: RoleName,
): Promise<Member> => {
  const updated = await api.patch<Omit<AdminUserWire, "sessionCount">>(
    `/auth/users/${userId}`,
    { role: roleWire(role) },
  );
  return toMember({ ...updated, sessionCount: 0 });
};

/* ── Invitations ─────────────────────────────────────────────────────────── */

/**
 * STUB (no endpoint yet): the hub has no invitation resource. `POST
 * /auth/users/invite` creates the *user* immediately, with an unusable
 * password, and hands back a one-shot reset token — there is nothing to list
 * and nothing to revoke. So the Invitations tab keeps a local, session-lived
 * record of what this browser has sent, seeded from fixtures, and says so.
 */
const INVITATION_STORE: Invitation[] = [...INVITATIONS];

// STUB (no endpoint yet): there is no GET /auth/invitations.
export const getInvitations = (): Promise<Invitation[]> =>
  after([...INVITATION_STORE], READ_DELAY_MS);

// STUB (no endpoint yet): there is no DELETE /auth/invitations/{email}.
// Dropping the local record does NOT delete the account the hub created —
// that is `DELETE /auth/users/{id}`, from User Management.
export const revokeInvitation = (email: string): Promise<void> => {
  const at = INVITATION_STORE.findIndex((i) => i.email === email);
  if (at >= 0) INVITATION_STORE.splice(at, 1);
  return after(undefined, READ_DELAY_MS);
};

/** `POST /auth/users/invite` returns the created user plus a reset token. */
interface InviteWire {
  user: { email: string; role: string };
  /** Echoed outside production only — email delivery is not wired yet. */
  resetToken: string | null;
}

/** The created invitation, plus the dev-only redemption link when we got one. */
export interface InviteResult {
  invitation: Invitation;
  /** Relative path to the reset screen, or null in production. */
  resetPath: string | null;
}

/**
 * `POST /auth/users/invite`. Creates the account with no usable password; the
 * invitee sets one through `/reset`. 409 if the email already exists — the
 * caller surfaces `ApiError.message` verbatim rather than guessing.
 */
export const invite = async (
  email: string,
  role: RoleName,
  by: string,
): Promise<InviteResult> => {
  const res = await api.post<InviteWire>("/auth/users/invite", {
    email,
    role: roleWire(role),
  });
  const invitation: Invitation = {
    email: res.user.email,
    role: roleName(res.user.role),
    sent: "just now",
    by,
  };
  INVITATION_STORE.unshift(invitation);
  return {
    invitation,
    resetPath: res.resetToken
      ? `/reset?token=${encodeURIComponent(res.resetToken)}`
      : null,
  };
};

/* ── Roles ───────────────────────────────────────────────────────────────── */

/**
 * STUB (no endpoint yet): there is no roles resource. The two real roles are an
 * enum on the user row, and the permission checklists this grid renders exist
 * nowhere but the design. Fixtures, labelled as preview data on the screen.
 */
export const getRoles = (): Promise<Role[]> => after(ROLES, READ_DELAY_MS);

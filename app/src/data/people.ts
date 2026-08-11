// People — workspace members, roles and pending invitations.
//
// Members and invitations are real; roles and the invitation LIST are not.
//
//   GET    /auth/users          getMembers
//   POST   /auth/users          createUser     usable immediately
//   PATCH  /auth/users/{id}     updateMember   role, name, active state
//   DELETE /auth/users/{id}     removeMember   hard delete
//   POST   /auth/users/invite   invite         usable once redeemed
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

/** `UserOut` — what the *mutating* routes return. It carries no session count. */
type UserWire = Omit<AdminUserWire, "sessionCount">;

const toMember = (wire: UserWire, sessionCount: number): Member => ({
  id: wire.id,
  name: displayNameFrom(wire.firstName, wire.lastName, wire.email),
  email: wire.email,
  role: roleName(wire.role),
  lastActive: relativeTime(wire.lastActive),
  initials: initialsFrom(wire.firstName, wire.lastName, wire.email),
  isActive: wire.isActive,
  sessionCount,
  // STUB (no endpoint yet): nothing on the hub maps a user to a Claude
  // credential, so this column reads "Not assigned" for every live row.
  credential: "none",
  credentialId: null,
});

/** `GET /auth/users`. Admin-only — a plain member gets a 403 here. */
export const getMembers = async (): Promise<Member[]> => {
  const rows = await api.get<AdminUserWire[]>("/auth/users");
  return rows.map((row) => toMember(row, row.sessionCount ?? 0));
};

/** The fields `PATCH /auth/users/{id}` accepts. Omitted keys are left alone. */
export interface MemberPatch {
  firstName?: string;
  lastName?: string;
  role?: RoleName;
  isActive?: boolean;
}

/**
 * `PATCH /auth/users/{id}` — every mutation the Members table makes: role,
 * name, and active state.
 *
 * Takes the whole `Member` rather than an id because the response carries no
 * `sessionCount` and the right value depends on what changed: deactivating
 * revokes the account's sessions server-side, so the count is 0 by
 * construction, while any other change leaves them untouched and the listed
 * count still holds. Deriving it here keeps that rule in one place instead of
 * leaving every caller to repair the row afterwards.
 *
 * The zero-active-admins guard is the hub's and stays the hub's — it is the only
 * party that can count admins correctly. `ApiError.message` carries a readable
 * reason for the caller to surface verbatim.
 */
export const updateMember = async (
  member: Member,
  patch: MemberPatch,
): Promise<Member> => {
  const body: Record<string, unknown> = {};
  if (patch.firstName !== undefined) body.firstName = patch.firstName;
  if (patch.lastName !== undefined) body.lastName = patch.lastName;
  if (patch.role !== undefined) body.role = roleWire(patch.role);
  if (patch.isActive !== undefined) body.isActive = patch.isActive;

  const updated = await api.patch<UserWire>(`/auth/users/${member.id}`, body);
  return toMember(updated, updated.isActive ? member.sessionCount : 0);
};

/**
 * `DELETE /auth/users/{id}` — a hard delete. The row goes, and its auth sessions
 * with it; the `identity` audit record keeps the email, so the trail outlives the
 * account.
 *
 * There is no soft-delete to fall back on, which is why the UI puts deactivation
 * first and gates this behind a typed confirmation. Refuses with 400 on the last
 * active admin — again the hub's count, not ours.
 */
export const removeMember = async (userId: number): Promise<void> => {
  await api.delete(`/auth/users/${userId}`);
};

/** What `POST /auth/users` needs. Names are optional; the hub defaults them to "". */
export interface NewUser {
  email: string;
  firstName?: string;
  lastName?: string;
  role: RoleName;
  password: string;
}

/**
 * `POST /auth/users` — create an account that is usable immediately, because the
 * admin sets the password.
 *
 * This is the difference from `invite`, and the reason both exist: an invitation
 * is only usable once the invitee redeems a reset token, and on a deployment
 * where email delivery is not wired that token has to be carried over by hand.
 * Direct creation is the right shape for a shared or service account, and for
 * handing someone working credentials in the room.
 *
 * 409 when the email is taken. The response is a plain `UserOut`, so the new row
 * starts with no sessions — nobody has signed in as them yet.
 */
export const createUser = async (input: NewUser): Promise<Member> => {
  const created = await api.post<UserWire>("/auth/users", {
    email: input.email,
    firstName: input.firstName ?? "",
    lastName: input.lastName ?? "",
    role: roleWire(input.role),
    password: input.password,
  });
  return toMember(created, 0);
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

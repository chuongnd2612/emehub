// People — workspace members, roles and pending invitations.
//
// STUBS. Each function names the endpoint that will replace it. The real ones
// are already implemented on the hub (`GET|POST /auth/users`,
// `POST /auth/users/invite`, `PATCH|DELETE /auth/users/{id}`); swapping them in
// is a later slice — deliberately not this one.

import { INVITATIONS, MEMBERS, ROLES } from "./fixtures/people";
import { after, READ_DELAY_MS } from "./timing";
import type { Invitation, Member, Role, RoleName } from "./types";

// STUB: GET /api/members
export const getMembers = (): Promise<Member[]> => after(MEMBERS, READ_DELAY_MS);

// STUB: GET /api/roles
export const getRoles = (): Promise<Role[]> => after(ROLES, READ_DELAY_MS);

/**
 * Pending invitations are the one collection two different surfaces mutate —
 * the global Invite modal creates, User Management revokes — so the stub keeps
 * its own mutable copy instead of handing the fixture array around.
 */
const INVITATION_STORE: Invitation[] = [...INVITATIONS];

// STUB: GET /api/invitations
export const getInvitations = (): Promise<Invitation[]> =>
  after([...INVITATION_STORE], READ_DELAY_MS);

// STUB: PATCH /api/members/{email}
export const changeRole = (email: string, role: RoleName): Promise<Member[]> =>
  after(
    MEMBERS.map((m) => (m.email === email ? { ...m, role } : m)),
    READ_DELAY_MS,
  );

// STUB: POST /api/invitations
export const invite = (email: string, role: RoleName): Promise<Invitation> => {
  const invitation: Invitation = {
    email,
    role,
    sent: "just now",
    by: "Emre Kaya",
  };
  INVITATION_STORE.unshift(invitation);
  return after(invitation, READ_DELAY_MS);
};

// STUB: DELETE /api/invitations/{email}
export const revokeInvitation = (email: string): Promise<void> => {
  const at = INVITATION_STORE.findIndex((i) => i.email === email);
  if (at >= 0) INVITATION_STORE.splice(at, 1);
  return after(undefined, READ_DELAY_MS);
};

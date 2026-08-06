// Auth — the signed-in principal, their password, their 2FA enrolment and
// their sessions. Every call here is real.
//
// The hub is the only place a token is minted or renewed (INTEGRATION.md §2),
// so this module never touches tokens directly: `lib/api.ts` owns the bearer
// header, the CSRF double-submit and the 401 → refresh → retry path, and
// `store/auth.ts` owns the in-memory access token.
//
// Endpoint map:
//   GET    /auth/me                     getMe
//   PATCH  /auth/me                     updateMe
//   POST   /auth/change-password        changePassword
//   POST   /auth/2fa/setup              startTotpSetup
//   POST   /auth/2fa/enable             enableTotp
//   POST   /auth/2fa/disable            disableTotp
//   GET    /auth/sessions               getSessions
//   DELETE /auth/sessions/{id}          revokeSession
//   POST   /auth/sessions/revoke-others revokeOtherSessions

import { api } from "@/lib/api";
import { describeUserAgent, relativeFuture, relativeTime } from "./humanize";
import { after, READ_DELAY_MS } from "./timing";
import type { AuthUser, Session, TotpSetup } from "./types";

/* ── The principal ───────────────────────────────────────────────────────── */

/** `GET /auth/me` — the current user, straight off the wire. */
export const getMe = (): Promise<AuthUser> => api.get<AuthUser>("/auth/me");

/** `PATCH /auth/me` — the only two fields a member may change about itself. */
export const updateMe = (patch: {
  firstName?: string;
  lastName?: string;
}): Promise<AuthUser> => api.patch<AuthUser>("/auth/me", patch);

/**
 * `POST /auth/change-password`. The hub keeps THIS session alive and revokes
 * every other one, so a caller showing a session list should re-read it after.
 */
export const changePassword = async (input: {
  currentPassword: string;
  newPassword: string;
}): Promise<void> => {
  await api.post("/auth/change-password", input);
};

/* ── Two-factor ──────────────────────────────────────────────────────────── */

/**
 * `POST /auth/2fa/setup` — mints an enrolment secret and returns it. This is
 * the only response in the whole API that contains the TOTP secret, so it must
 * never be logged or persisted: hold it in component state until `enableTotp`
 * confirms, then drop it.
 */
export const startTotpSetup = (): Promise<TotpSetup> =>
  api.post<TotpSetup>("/auth/2fa/setup");

/** `POST /auth/2fa/enable` — verifies a code against the pending secret. */
export const enableTotp = async (code: string): Promise<void> => {
  await api.post("/auth/2fa/enable", { code });
};

/** `POST /auth/2fa/disable` — accepts either a live code or the password. */
export const disableTotp = async (proof: {
  code?: string;
  password?: string;
}): Promise<void> => {
  await api.post("/auth/2fa/disable", proof);
};

/* ── Sessions ────────────────────────────────────────────────────────────── */

/** `SessionOut` as the hub sends it. Mapped to `Session` for the screens. */
interface SessionWire {
  id: string;
  userAgent: string;
  ip: string;
  createdAt: string | null;
  lastSeenAt: string | null;
  expiresAt: string | null;
  current: boolean;
}

const toSession = (wire: SessionWire): Session => ({
  id: wire.id,
  device: describeUserAgent(wire.userAgent),
  userAgent: wire.userAgent,
  ip: wire.ip || "unknown",
  when: relativeTime(wire.lastSeenAt ?? wire.createdAt),
  expires: relativeFuture(wire.expiresAt),
  current: wire.current,
});

/**
 * `GET /auth/sessions`. There is no geo lookup on the hub, so the prototype's
 * "where" column has no source and the mapped `Session` drops it.
 */
export const getSessions = async (): Promise<Session[]> => {
  const rows = await api.get<SessionWire[]>("/auth/sessions");
  return rows.map(toSession);
};

/** `DELETE /auth/sessions/{id}`. The current session is not revocable here. */
export const revokeSession = async (id: string): Promise<void> => {
  await api.delete(`/auth/sessions/${encodeURIComponent(id)}`);
};

/** `POST /auth/sessions/revoke-others` — signs out every device but this one. */
export const revokeOtherSessions = async (): Promise<void> => {
  await api.post("/auth/sessions/revoke-others");
};

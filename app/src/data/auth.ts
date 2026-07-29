// Auth — sessions and API keys as the Auth screen consumes them.
//
// STUBS. The hub now really implements `GET /auth/sessions`,
// `DELETE /auth/sessions/{id}` and `POST /auth/sessions/revoke-others`, but
// swapping these over is a later slice — this issue only prepares the seam.
// Note the shapes differ: the real `SessionOut` is
// `{id, userAgent, ip, createdAt, lastSeenAt, expiresAt, current}`, so the swap
// is a mapping, not a rename.

import { API_KEYS, SESSIONS } from "./fixtures/auth";
import { after, READ_DELAY_MS } from "./timing";
import type { ApiKey, Session } from "./types";

// STUB: GET /api/auth/sessions
export const getSessions = (): Promise<Session[]> =>
  after(SESSIONS, READ_DELAY_MS);

// STUB: GET /api/auth/api-keys
export const getApiKeys = (): Promise<ApiKey[]> => after(API_KEYS, READ_DELAY_MS);

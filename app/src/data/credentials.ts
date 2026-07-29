// Claude credentials — the one secret the hub deliberately hands out
// (INTEGRATION.md §4). Two halves:
//
//  1. REAL `.credentials.json` parsing, client-side (Handoff › 6. Claude
//     Settings › Credentials › "Real file parsing"): accept `claudeAiOauth` |
//     `claude_ai_oauth` | the root object, require `accessToken`/
//     `access_token`, read `expiresAt`/`expires_at` (epoch ms) -> days left,
//     `scopes`, `subscriptionType`. An unparseable file is rejected here and
//     never reaches the network.
//  2. REAL calls to the hub for everything stored.
//
// Endpoint map:
//   GET    /credentials/claude          getCredentialState
//   PUT    /credentials/claude          uploadOwnCredential
//   DELETE /credentials/claude          deleteOwnCredential
//   PUT    /credentials/claude/mode     setCredentialMode
//   PUT    /credentials/claude/shared   uploadSharedCredential
//   DELETE /credentials/claude/shared   deleteSharedCredential
//   POST   /credentials/claude/test     testCredential
//   GET    /credentials/claude/usage    getClaudeUsage
//
// ## What the hub will NOT tell the SPA
//
// No response here carries credential material. `CredentialMetaOut` is
// metadata only — there is no masked token, no `token` field, nothing to
// reveal. The single credential-bearing endpoint is
// `GET /credentials/claude/resolve`, which exists for the agents and is
// deliberately not called from this module.
//
// The hub stores **one** own credential per user and **one** shared workspace
// credential — not a list. `getSharedCredentials()` survives as a thin adapter
// for the header popover, which was written against the list shape.

import { api } from "@/lib/api";
import { relativeFuture, relativeTime } from "./humanize";
import type {
  CredentialStatus,
  PersonalCredential,
  SharedCredential,
} from "./types";

/** Toast copy for an unparseable file. Copy is final — do not paraphrase. */
export const INVALID_CREDENTIAL_TOAST = {
  title: "Invalid .credentials.json",
  body: "Expected a claudeAiOauth token object",
} as const;

// The handoff's 850 ms "Reading token…" dwell was a prototype timing. The real
// PUT replaces it — the spinner now runs for exactly as long as the request.

export interface ParsedCredential {
  token: string;
  /** Expiry as epoch milliseconds, or null when the token never expires. */
  expiresAtEpochMs: number | null;
  scopes: string[];
  subscription: string;
  filename: string;
  /**
   * Whether the file carried a `refreshToken`. **The presence, not the token**
   * — nothing here lifts the refresh token out of the file, so there is no
   * field anywhere that could be logged or posted by accident. Drives
   * {@link derivedCredentialStatus}; see issue #63.
   */
  hasRefreshToken: boolean;
}

export class InvalidCredentialFileError extends Error {
  constructor(message = "Expected a claudeAiOauth token object") {
    super(message);
    this.name = "InvalidCredentialFileError";
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asEpochMs(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

/**
 * Parse the text of a `.credentials.json`.
 * @throws InvalidCredentialFileError when the JSON is malformed or has no token.
 */
export function parseCredentialJson(
  text: string,
  filename = ".credentials.json",
): ParsedCredential {
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch {
    throw new InvalidCredentialFileError();
  }

  const root = asRecord(json);
  if (!root) throw new InvalidCredentialFileError();

  // Accept the wrapped shapes the Claude CLI has used, or the bare object.
  const o =
    asRecord(root["claudeAiOauth"]) ?? asRecord(root["claude_ai_oauth"]) ?? root;

  const token = asString(o["accessToken"]) ?? asString(o["access_token"]);
  if (!token) throw new InvalidCredentialFileError();

  const expiresAtEpochMs =
    asEpochMs(o["expiresAt"]) ?? asEpochMs(o["expires_at"]) ?? null;

  const rawScopes = o["scopes"];
  const scopes =
    Array.isArray(rawScopes) && rawScopes.length > 0
      ? rawScopes.filter((s): s is string => typeof s === "string")
      : ["user:inference"];

  const subscription =
    asString(o["subscriptionType"]) ??
    asString(o["subscription"]) ??
    "Claude account";

  // Presence only — converted straight to a boolean, the string dropped.
  const hasRefreshToken = Boolean(
    asString(o["refreshToken"]) ?? asString(o["refresh_token"]),
  );

  return {
    token,
    expiresAtEpochMs,
    scopes: scopes.length > 0 ? scopes : ["user:inference"],
    subscription,
    filename,
    hasRefreshToken,
  };
}

/** Read + parse a dropped File. Rejects with InvalidCredentialFileError. */
export function parseCredentialFile(file: File): Promise<ParsedCredential> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new InvalidCredentialFileError());
    reader.onload = () => {
      try {
        resolve(parseCredentialJson(String(reader.result), file.name));
      } catch (err) {
        reject(err);
      }
    };
    reader.readAsText(file);
  });
}

/** Whole days between now and the expiry. Null when there is no expiry. */
export function daysLeftFrom(
  expiresAtEpochMs: number | null,
  now: number = Date.now(),
): number | null {
  if (!expiresAtEpochMs) return null;
  return Math.round((expiresAtEpochMs - now) / 86_400_000);
}

/**
 * The derived status rule, verbatim from the handoff:
 * `daysLeft == null ? 'active' : daysLeft < 0 ? 'expired' : daysLeft <= 2 ? 'expiring' : 'active'`
 */
export function credentialStatus(daysLeft: number | null): CredentialStatus {
  if (daysLeft == null) return "active";
  if (daysLeft < 0) return "expired";
  if (daysLeft <= 2) return "expiring";
  return "active";
}

/** One stored credential, reduced to what the status rule needs. */
export interface CredentialStatusInput {
  /** Epoch ms, or null when the token never expires. */
  expiresAtEpochMs: number | null;
  /** Whether a refresh token sits beside the access token in the file. */
  hasRefreshToken: boolean;
  /**
   * The hub's *stored* status column. `"expired"` here means the Claude CLI
   * actually rejected the credential (`_mark_credential_invalid`), which is the
   * one authoritative "does not work" signal and wins over everything derived.
   */
  storedStatus?: string;
}

/**
 * The effective status, mirroring `derived_status` in
 * `api/app/services/claude_credentials.py` so the client-side parse of a
 * dropped file and the hub's own answer never disagree. Precedence:
 *
 *   1. a stored `expired` — the CLI's verdict, authoritative;
 *   2. elapsed expiry **with** a refresh token -> `refreshable` (the CLI renews
 *      it on the next run; issue #63);
 *   3. otherwise {@link credentialStatus}, the handoff's rule, verbatim — so
 *      `expired` is derived from the clock only when there is no refresh token.
 *
 * Step 2 tests the timestamp directly rather than `daysLeft < 0`, because
 * `daysLeft` rounds: a token that lapsed three hours ago reports `0` days, and
 * three-hours-past-expiry is the state a real `.credentials.json` is usually in.
 */
export function derivedCredentialStatus(
  input: CredentialStatusInput,
  now: number = Date.now(),
): CredentialStatus {
  if (input.storedStatus === "expired") return "expired";
  const expiry = input.expiresAtEpochMs;
  if (input.hasRefreshToken && expiry != null && expiry < now) {
    return "refreshable";
  }
  return credentialStatus(daysLeftFrom(expiry, now));
}

/** "12 Oct 2026" — the expiry format used across the credential cards. */
export function formatExpiry(expiresAtEpochMs: number | null): string {
  if (!expiresAtEpochMs) return "—";
  try {
    return new Date(expiresAtEpochMs).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return "—";
  }
}

/** "in 76 days" / "in 1 day" / "today" / "3 days ago" / "—". */
export function formatDaysLeft(daysLeft: number | null): string {
  if (daysLeft == null) return "—";
  if (daysLeft < 0) return `${Math.abs(daysLeft)} days ago`;
  if (daysLeft === 0) return "today";
  if (daysLeft === 1) return "in 1 day";
  return `in ${daysLeft} days`;
}

/** `first16••••••••••••last4` — the masked ACCESS TOKEN row. */
export function maskToken(token: string | null | undefined): string {
  if (!token) return "—";
  return `${token.slice(0, 16)}••••••••••••${token.slice(-4)}`;
}

/** Turn a parsed file into the shape the personal-credential card renders. */
export function toPersonalCredential(
  parsed: ParsedCredential,
  now: number = Date.now(),
): PersonalCredential {
  return {
    filename: parsed.filename,
    subscription: parsed.subscription,
    scopes: parsed.scopes,
    token: parsed.token,
    expiresDisplay: formatExpiry(parsed.expiresAtEpochMs),
    daysLeft: daysLeftFrom(parsed.expiresAtEpochMs, now),
    lastRefreshed: "just now",
  };
}

/**
 * Read a dropped file, parse it, and hand back BOTH the parsed metadata and the
 * raw text — the hub stores the original blob, so the upload calls need it.
 *
 * The parse happens first and throws on a bad file, which is the point: an
 * invalid `.credentials.json` must never reach the network.
 *
 * @throws InvalidCredentialFileError
 */
export async function readCredentialFile(
  file: File,
): Promise<{ raw: string; parsed: ParsedCredential }> {
  const raw = await file.text().catch(() => {
    throw new InvalidCredentialFileError();
  });
  return { raw, parsed: parseCredentialJson(raw, file.name) };
}

/* ── The stored credential ────────────────────────────────────────────────
 *
 * Everything below talks to the hub for real. Nothing below can return a
 * token: no response model in `api/app/routers/credentials.py` reachable from
 * here has a credential-bearing field. */

/** Which credential a run would actually authenticate with. */
export type CredentialMode = "own" | "shared" | "none";

/** `CredentialMetaOut` — metadata for one stored credential, never the token. */
export interface ClaudeCredentialMeta {
  label: string;
  /** Derived server-side from the expiry; same rule as `credentialStatus`. */
  status: CredentialStatus;
  /** The status column as stored, before the expiry rule is re-applied. */
  storedStatus: string;
  /** ISO timestamp, or null when the token never expires. */
  expiresAt: string | null;
  daysLeft: number | null;
  scopes: string[];
  subscriptionType: string | null;
  /** ISO timestamp of the last write, including agent token rotation. */
  lastRefreshed: string | null;
  preferShared: boolean;
  /**
   * Whether the stored file carries a refresh token — the presence, never the
   * token. Feeds {@link statusOfCredential}; see issue #63.
   */
  hasRefreshToken: boolean;
  /** Shared row only — active users running on it because they have no own. */
  assignedUsers: number | null;
}

/**
 * The effective status of a stored credential, applying the same rule the hub
 * just applied server-side. `meta.status` already carries the hub's answer;
 * this recomputes it locally so a stale payload, or a file parsed in the
 * browser before it has been uploaded, still agrees with the server.
 */
export const statusOfCredential = (
  meta: ClaudeCredentialMeta,
  now: number = Date.now(),
): CredentialStatus =>
  derivedCredentialStatus(
    {
      expiresAtEpochMs: meta.expiresAt ? Date.parse(meta.expiresAt) : null,
      hasRefreshToken: meta.hasRefreshToken,
      storedStatus: meta.storedStatus,
    },
    now,
  );

/** `GET /credentials/claude` — what is configured and what will be used. */
export interface ClaudeCredentialState {
  hasOwn: boolean;
  hasShared: boolean;
  mode: CredentialMode;
  preferShared: boolean;
  own: ClaudeCredentialMeta | null;
  shared: ClaudeCredentialMeta | null;
}

/** `POST /credentials/claude/test`. A STORAGE test — the hub never calls Claude. */
export interface CredentialTestOutcome {
  ok: boolean;
  /** `no_credential | undecryptable | invalid | expired | ok`. */
  result: string;
  message: string;
}

/** `GET /credentials/claude/usage` — the signed-in user's own spend. */
export interface ClaudeUsage {
  requestsToday: number;
  avgLatencyMs: number;
  costMonth: number;
  /** Tokens across the current week; the breakdown covers the same window. */
  weekTokens: number;
  weekResetsAt: string;
  breakdown: {
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite: number;
  };
}

const CREDENTIAL_PATH = "/credentials/claude";

/** `GET /credentials/claude`. */
export const getCredentialState = (): Promise<ClaudeCredentialState> =>
  api.get<ClaudeCredentialState>(CREDENTIAL_PATH);

/**
 * `PUT /credentials/claude` — upload or replace the caller's own credential.
 * Parses client-side first; an invalid file rejects before any request.
 */
export const uploadOwnCredential = async (
  file: File,
): Promise<ClaudeCredentialState> => {
  const { raw, parsed } = await readCredentialFile(file);
  return api.put<ClaudeCredentialState>(CREDENTIAL_PATH, {
    credentials: raw,
    label: parsed.filename,
  });
};

/** `DELETE /credentials/claude` — falls the caller back to the shared account. */
export const deleteOwnCredential = async (): Promise<void> => {
  await api.delete(CREDENTIAL_PATH);
};

/**
 * `PUT /credentials/claude/mode` — run under `own` or `shared` without
 * deleting either. The hub 400s when there is no own credential to store the
 * preference on, or when `shared` has nothing to fall back to.
 */
export const setCredentialMode = (
  mode: "own" | "shared",
): Promise<ClaudeCredentialState> =>
  api.put<ClaudeCredentialState>(`${CREDENTIAL_PATH}/mode`, { mode });

/** `PUT /credentials/claude/shared` — admin only; 403 for a member. */
export const uploadSharedCredential = async (
  file: File,
): Promise<ClaudeCredentialState> => {
  const { raw, parsed } = await readCredentialFile(file);
  return api.put<ClaudeCredentialState>(`${CREDENTIAL_PATH}/shared`, {
    credentials: raw,
    label: parsed.filename,
  });
};

/** `DELETE /credentials/claude/shared` — admin only. */
export const deleteSharedCredential = async (): Promise<void> => {
  await api.delete(`${CREDENTIAL_PATH}/shared`);
};

/**
 * `POST /credentials/claude/test`. Checks the stored credential is present,
 * decryptable, parseable and unexpired — the hub does not call Claude, so this
 * is not a liveness probe and there is no HTTP status or latency to report.
 */
export const testCredential = (
  scope: "effective" | "own" | "shared" = "effective",
): Promise<CredentialTestOutcome> =>
  api.post<CredentialTestOutcome>(`${CREDENTIAL_PATH}/test`, undefined, {
    query: { scope },
  });

/** `GET /credentials/claude/usage`. */
export const getClaudeUsage = (): Promise<ClaudeUsage> =>
  api.get<ClaudeUsage>(`${CREDENTIAL_PATH}/usage`);

/* ── Adapter for the header popover ──────────────────────────────────────── */

/** ISO expiry -> "12 Oct 2026". */
export const formatExpiryIso = (iso: string | null): string =>
  formatExpiry(iso ? Date.parse(iso) : null);

/**
 * ISO -> "26m ago" / "never". `humanize.ts` is data-layer scaffolding rather
 * than public API, so the screens reach it through here.
 */
export const formatRefreshed = (iso: string | null): string =>
  relativeTime(iso);

/** ISO -> "in 4d". Used for the usage window's reset. */
export const formatResetsIn = (iso: string | null): string =>
  relativeFuture(iso);

/**
 * The shared credential in the list shape `components/overlays/
 * ClaudeCredentialPopover` was written against. The hub holds at most one, so
 * this is a zero- or one-element list.
 *
 * `token` is the empty string on purpose: the hub returns no credential
 * material to the SPA, and the popover does not render it.
 */
export const getSharedCredentials = async (): Promise<SharedCredential[]> => {
  const state = await getCredentialState();
  const meta = state.shared;
  if (!meta) return [];
  return [
    {
      id: "shared",
      label: meta.label || "Shared Claude account",
      email: "—",
      subscription: meta.subscriptionType ?? "Claude account",
      expiresDisplay: formatExpiryIso(meta.expiresAt),
      daysLeft: meta.daysLeft,
      expiresAtEpochMs: meta.expiresAt ? Date.parse(meta.expiresAt) : null,
      hasRefreshToken: meta.hasRefreshToken,
      storedStatus: meta.storedStatus,
      scopes: meta.scopes,
      lastRefreshed: relativeTime(meta.lastRefreshed),
      members: meta.assignedUsers ?? 0,
      isDefault: true,
      token: "",
      source: meta.label || ".credentials.json",
    },
  ];
};

/* ── Not implemented by the hub ──────────────────────────────────────────── */

/** Why "Set as default" is offered but disabled. Shown in the credential menu. */
export const SET_DEFAULT_UNAVAILABLE =
  "The hub holds a single shared account, so there is nothing to choose between";

/**
 * STUB (no endpoint yet): there is no route that marks one credential the
 * default — verified against `/api/openapi.json`. The hub's model is one shared
 * credential for the workspace plus one own credential per user, resolved
 * own → shared → none, so "default" has no server-side meaning yet.
 *
 * Deliberately rejects rather than resolving: nothing may call this and appear
 * to have worked. The UI shows the action disabled with
 * {@link SET_DEFAULT_UNAVAILABLE} as the reason.
 */
export const setDefaultCredential = (_credentialId: string): Promise<never> =>
  Promise.reject(new Error(SET_DEFAULT_UNAVAILABLE));

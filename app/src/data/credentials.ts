// REAL `.credentials.json` parsing — not a stub.
//
// Handoff › 6. Claude Settings › Credentials › "Real file parsing": read the
// dropped JSON, accept `claudeAiOauth` | `claude_ai_oauth` | the root object,
// require `accessToken`/`access_token`, read `expiresAt`/`expires_at` (epoch
// ms) -> days left, `scopes`, `subscriptionType`.
//
// The file the user drops is the same one the agents need at
// `~/.claude/.credentials.json` before each run (INTEGRATION.md §4).

import type { CredentialStatus, PersonalCredential } from "./types";

/** Toast copy for an unparseable file. Copy is final — do not paraphrase. */
export const INVALID_CREDENTIAL_TOAST = {
  title: "Invalid .credentials.json",
  body: "Expected a claudeAiOauth token object",
} as const;

/** Spinner dwell after a successful parse (Handoff › Async behaviours). */
export const CREDENTIAL_UPLOAD_DELAY_MS = 850;

export interface ParsedCredential {
  token: string;
  /** Expiry as epoch milliseconds, or null when the token never expires. */
  expiresAtEpochMs: number | null;
  scopes: string[];
  subscription: string;
  filename: string;
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

  return {
    token,
    expiresAtEpochMs,
    scopes: scopes.length > 0 ? scopes : ["user:inference"],
    subscription,
    filename,
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

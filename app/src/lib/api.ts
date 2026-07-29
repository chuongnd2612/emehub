// The typed HTTP client for the EmeHub API.
//
// Nothing calls this yet — `data/*` is still stubbed against fixtures, and
// swapping a resource module over to a real call is a later slice. This exists
// so each of those slices inherits one place where the awkward parts already
// work: the bearer header, the 401 → refresh → retry-once path, and the CSRF
// double-submit the refresh endpoint requires.
//
// ## Where the access token lives
//
// In memory, deliberately — never `localStorage` or `sessionStorage`, which any
// injected script can read. Losing it on reload is fine: the refresh cookie is
// HttpOnly and `POST /auth/refresh` mints a new one. The refresh token itself is
// never visible to JavaScript at all.
//
// ## Contract notes (docs/INTEGRATION.md §2)
//
// Access tokens live 15 minutes and are audience-scoped; the SPA uses the
// `emehub` one. Refresh happens **only** at the hub — an agent must never issue,
// refresh or extend a token.

/** Prefix for every request. Same-origin by default; see `vite-env.d.ts`. */
export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

/** Readable CSRF cookie, echoed back in the header on refresh. */
const CSRF_COOKIE = "emehub_csrf";
const CSRF_HEADER = "X-CSRF-Token";

const REFRESH_PATH = "/auth/refresh";

/**
 * Endpoints where a 401 is the ANSWER, not a stale-token problem.
 *
 * `POST /auth/login` answers a wrong password with 401 "Invalid email or
 * password"; `POST /auth/login/mfa` answers a wrong code the same way. Running
 * those through the refresh-and-retry path is wrong twice over: it replaces the
 * hub's message with "Not authenticated", and it fires the unauthenticated
 * handler — signing out a visitor who was never signed in — on nothing worse
 * than a typo. Both were observed live before this list existed.
 */
const NO_REFRESH_PATHS = new Set([
  "/auth/login",
  "/auth/login/mfa",
  "/auth/request-reset",
  "/auth/reset",
  REFRESH_PATH,
]);

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `Request failed with ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** The user is not (or no longer) authenticated — refresh already failed. */
export class UnauthenticatedError extends ApiError {
  constructor(detail: unknown = null) {
    super(401, detail, "Not authenticated");
    this.name = "UnauthenticatedError";
  }
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  /** JSON-serialised into the body; sets `Content-Type` for you. */
  json?: unknown;
  /** Sent as-is (FormData, Blob, string). Mutually exclusive with `json`. */
  body?: BodyInit | null;
  /** Appended as a query string, skipping null/undefined values. */
  query?: Record<string, string | number | boolean | null | undefined>;
  /** Skip the 401 → refresh → retry path (used by the refresh call itself). */
  skipRefresh?: boolean;
}

/* ── Token state ─────────────────────────────────────────────────────────── */

let accessToken: string | null = null;
let onUnauthenticated: (() => void) | null = null;

export const setAccessToken = (token: string | null): void => {
  accessToken = token;
};

export const getAccessToken = (): string | null => accessToken;

/**
 * Called once when refresh fails and the session is genuinely over — the shell
 * registers a handler that routes to the login screen.
 */
export const setUnauthenticatedHandler = (handler: (() => void) | null): void => {
  onUnauthenticated = handler;
};

/* ── Internals ───────────────────────────────────────────────────────────── */

const readCookie = (name: string): string | null => {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : null;
};

const buildUrl = (path: string, query?: RequestOptions["query"]): string => {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value == null) continue;
    params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
};

const parseBody = async (response: Response): Promise<unknown> => {
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return null;
  }
  const type = response.headers.get("content-type") ?? "";
  if (type.includes("application/json")) {
    return response.json().catch(() => null);
  }
  return response.text();
};

const send = async (path: string, options: RequestOptions): Promise<Response> => {
  const { json, query, skipRefresh: _skip, headers, body, ...rest } = options;
  const merged = new Headers(headers);
  if (accessToken) merged.set("Authorization", `Bearer ${accessToken}`);
  if (json !== undefined && !merged.has("Content-Type")) {
    merged.set("Content-Type", "application/json");
  }
  return fetch(buildUrl(path, query), {
    ...rest,
    headers: merged,
    // The refresh cookie is HttpOnly and same-origin; it must ride along.
    credentials: "include",
    body: json !== undefined ? JSON.stringify(json) : (body ?? null),
  });
};

/**
 * One shared refresh in flight at a time. Without this, a screen firing five
 * requests on mount would fire five refreshes, and four of them would present
 * an already-rotated refresh token and fail.
 */
let refreshInFlight: Promise<boolean> | null = null;

/**
 * `POST /auth/refresh` with the CSRF double-submit the endpoint requires.
 *
 * Exported because the session store's `bootstrap()` needs the same call — the
 * refresh endpoint is the one route whose headers are not derivable from the
 * generic client, and having two copies of the double-submit is how one of them
 * ends up wrong. Installs the returned access token as a side effect, so the
 * caller only has to read `user` off the body.
 *
 * Throws `ApiError` on any non-2xx (a missing/rotated cookie is a 401, a
 * missing CSRF header a 403).
 */
export async function refreshSession<T = unknown>(): Promise<T> {
  const csrf = readCookie(CSRF_COOKIE);
  const response = await send(REFRESH_PATH, {
    method: "POST",
    skipRefresh: true,
    headers: csrf ? { [CSRF_HEADER]: csrf } : undefined,
  });
  const body = await parseBody(response);
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(
      response.status,
      detail,
      typeof detail === "string" ? detail : undefined,
    );
  }
  const token = (body as { accessToken?: string } | null)?.accessToken;
  if (token) setAccessToken(token);
  return body as T;
}

const refreshAccessToken = async (): Promise<boolean> => {
  refreshInFlight ??= (async () => {
    try {
      const body = await refreshSession<{ accessToken?: string }>();
      return Boolean(body?.accessToken);
    } catch {
      return false;
    } finally {
      // Cleared on the next tick so concurrent callers all see this attempt.
      queueMicrotask(() => {
        refreshInFlight = null;
      });
    }
  })();
  return refreshInFlight;
};

/* ── The client ──────────────────────────────────────────────────────────── */

/**
 * Perform a request and decode the JSON body.
 *
 * On 401 it refreshes once and retries the original request exactly once — a
 * second 401 means the session is over, so it clears the token, notifies the
 * handler and throws {@link UnauthenticatedError}. It never loops.
 *
 * The public auth endpoints in {@link NO_REFRESH_PATHS} are exempt: their 401
 * is a real answer and is surfaced as a plain {@link ApiError} carrying the
 * hub's own message.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  let response = await send(path, options);

  if (
    response.status === 401 &&
    !options.skipRefresh &&
    !NO_REFRESH_PATHS.has(path)
  ) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await send(path, { ...options, skipRefresh: true });
    }
    if (response.status === 401) {
      setAccessToken(null);
      onUnauthenticated?.();
      throw new UnauthenticatedError(await parseBody(response));
    }
  }

  const body = await parseBody(response);
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(
      response.status,
      detail,
      typeof detail === "string" ? detail : undefined,
    );
  }
  return body as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", json }),
  patch: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", json }),
  put: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PUT", json }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
} as const;

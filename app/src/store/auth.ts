// The session store — who is signed in, and whether we know yet.
//
// Companion to `store/ui.ts`, but for the authenticated principal rather than
// ephemeral UI. Navigation still belongs to the URL (CLAUDE.md › Frontend
// conventions): this store never says *which screen*, only *whether there is a
// session*. `RequireAuth` / `RedirectIfAuthed` turn that into a `<Navigate>`.
//
// ## Where the access token lives — and why it is not in here
//
// The access token is held in ONE place: the module-scope variable inside
// `lib/api.ts` (`setAccessToken` / `getAccessToken`). Never localStorage, never
// sessionStorage, and deliberately not in this store either — Zustand state is
// enumerable, snapshot-able by devtools and easy to spread into a log line by
// accident. Nothing outside `lib/api.ts` needs the token: the client attaches
// the bearer header itself.
//
// The durable credential is the hub's HttpOnly `emehub_refresh` cookie, which
// JavaScript cannot read at all. A hard reload therefore starts with no access
// token and `status: "idle"`; `bootstrap()` exchanges the cookie for a fresh
// one (`POST /auth/refresh`, CSRF double-submit handled by `lib/api.ts`).
//
// ## The hard-401 bridge
//
// `lib/api.ts` calls the handler registered below exactly once, when a refresh
// has already failed and the session is genuinely over. It flips the store to
// "anon"; the guards react by rendering `<Navigate to="/login">`. It never
// navigates imperatively, so it cannot loop.

import { create } from "zustand";

import { getMe } from "@/data/auth";
import { displayNameFrom, initialsFrom } from "@/data/humanize";
import { roleName } from "@/data/people";
import type { AuthUser, LoginOutcome, RoleName } from "@/data/types";
import {
  api,
  refreshSession,
  setAccessToken,
  setUnauthenticatedHandler,
} from "@/lib/api";

/**
 * - `idle`    nothing has been attempted yet (fresh load)
 * - `loading` a bootstrap/refresh is in flight
 * - `authed`  we hold a live access token and a principal
 * - `anon`    there is no session; the guards may redirect
 */
export type AuthStatus = "idle" | "loading" | "authed" | "anon";

/** `LoginResponse` / `RefreshResponse` — the two share these fields. */
interface SessionWire {
  accessToken?: string | null;
  user?: AuthUser | null;
  mfaRequired?: boolean;
  mfaToken?: string | null;
}

export interface AuthState {
  /** The signed-in principal, or null when there is no session. */
  user: AuthUser | null;
  status: AuthStatus;

  /**
   * Exchange the refresh cookie for an access token. Safe to call whenever
   * `status === "idle"`; concurrent calls collapse onto the in-flight one.
   */
  bootstrap: () => Promise<void>;

  /**
   * `POST /auth/login`. Resolves to a discriminated outcome rather than
   * throwing on the MFA branch — the caller must handle both:
   *
   *   const out = await login({ email, password, remember });
   *   if (out.kind === "mfa") setMfaToken(out.mfaToken); else navigate("/app");
   *
   * Throws `ApiError` (401 "Invalid email or password") on a bad credential.
   */
  login: (input: {
    email: string;
    password: string;
    remember?: boolean;
  }) => Promise<LoginOutcome>;

  /** `POST /auth/login/mfa` — step 2, with the token `login` handed back. */
  loginMfa: (input: { mfaToken: string; code: string }) => Promise<AuthUser>;

  /**
   * `POST /auth/logout` — revokes this session server-side and clears the
   * cookies, then drops local state. Never rejects: a failed network call must
   * still sign you out of this tab.
   */
  logout: () => Promise<void>;

  /** Drop local state without calling the hub (a dead session, a hard 401). */
  clear: () => void;

  /**
   * Re-read `GET /auth/me` into the store — call after anything that changes
   * the principal (profile save, 2FA enable/disable). Silently keeps the
   * last-known user if the read fails.
   */
  refreshUser: () => Promise<void>;

  /** Replace the principal from a payload you already have. */
  setUser: (user: AuthUser) => void;
}

/** Collapses concurrent bootstrap calls onto one refresh. */
let bootstrapInFlight: Promise<void> | null = null;

const install = (wire: SessionWire): AuthUser => {
  if (!wire.accessToken || !wire.user) {
    throw new Error("The hub returned a session with no token or user.");
  }
  setAccessToken(wire.accessToken);
  useAuth.setState({ user: wire.user, status: "authed" });
  return wire.user;
};

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  status: "idle",

  bootstrap: () => {
    if (get().status === "loading" && bootstrapInFlight) return bootstrapInFlight;
    set({ status: "loading" });
    bootstrapInFlight = (async () => {
      try {
        // `refreshSession` (not `api.post`) because the refresh endpoint needs
        // the CSRF double-submit header, and it already installs the token.
        install(await refreshSession<SessionWire>());
      } catch {
        setAccessToken(null);
        set({ user: null, status: "anon" });
      } finally {
        bootstrapInFlight = null;
      }
    })();
    return bootstrapInFlight;
  },

  login: async ({ email, password, remember = true }) => {
    const wire = await api.post<SessionWire>("/auth/login", {
      email,
      password,
      remember,
    });
    // Discriminate on a TRUTHY `mfaRequired`: a straight success also carries
    // `mfaRequired: false` + `mfaToken: null`.
    if (wire.mfaRequired && wire.mfaToken) {
      return { kind: "mfa", mfaToken: wire.mfaToken };
    }
    return { kind: "authed", user: install(wire) };
  },

  loginMfa: async ({ mfaToken, code }) => {
    const wire = await api.post<SessionWire>("/auth/login/mfa", {
      mfaToken,
      code,
    });
    return install(wire);
  },

  logout: async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // The cookie may already be dead. Signing out locally is the point.
    }
    get().clear();
  },

  clear: () => {
    setAccessToken(null);
    set({ user: null, status: "anon" });
  },

  refreshUser: async () => {
    try {
      set({ user: await getMe(), status: "authed" });
    } catch {
      // Non-fatal: keep the last-known principal. A genuinely dead session is
      // handled by the unauthenticated bridge below, not here.
    }
  },

  setUser: (user) => set({ user, status: "authed" }),
}));

/**
 * The hard-401 bridge. Registered once, at module load, so it is installed
 * before any screen can fire a request. `lib/api.ts` only reaches this after a
 * refresh has already failed.
 */
setUnauthenticatedHandler(() => {
  setAccessToken(null);
  useAuth.setState({ user: null, status: "anon" });
});

/* ── Selectors ───────────────────────────────────────────────────────────── */

/** "Emre Kaya", or the email's local part when the name is unset. */
export const displayName = (user: AuthUser | null): string =>
  user ? displayNameFrom(user.firstName, user.lastName, user.email) : "";

/** "EK" for the avatar tile. */
export const userInitials = (user: AuthUser | null): string =>
  user ? initialsFrom(user.firstName, user.lastName, user.email) : "?";

/** "Admin" / "Member" — the display name of the hub's raw role. */
export const userRole = (user: AuthUser | null): RoleName | null =>
  user ? roleName(user.role) : null;

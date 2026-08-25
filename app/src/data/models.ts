// Model preferences — the Claude model and effort a member's runs use.
//
//   GET /me/model-preferences    getModelPreferences
//   PUT /me/model-preferences    setModelPreferences
//
// LIVE. This replaced four `useState`s on the Models tab of Claude Settings that
// persisted nowhere and were read by nothing (#190).
//
// It is not a display setting: the hub's own knowledge builds resolve their
// model and their `claude --effort` level from the row owner's preferences
// before invoking the CLI (`api/app/services/model_preferences.py` ›
// `resolve_for_run`). Picking a model here changes what the next build runs on.
//
// The wire carries model **ids** (`claude-opus-5`), never display labels. The
// labels and context windows live in `screens/Claude/state.ts` because they are
// copy; the hub validates the id and stays out of the naming.
//
// ## Why a change signal, and why a bare counter
//
// Same shape as `credentials.ts`, and for the same reason: the header chip
// reports what a run would use, and a chip that keeps describing the previous
// selection until the page is reloaded is worse than one that says nothing —
// nothing about it looks stale. Every write below announces itself, so a reader
// only has to subscribe.
//
// The signal is a revision counter rather than the state itself so that two
// subscribers can never disagree; re-reading is one cheap request. (The app uses
// Zustand for UI state and has no query cache to invalidate, so there is nothing
// else this could hook into.)

import { api } from "@/lib/api";

const PATH = "/me/model-preferences";

/** Model ids and a `claude --effort` level, as stored by the hub. */
export interface ModelPreferences {
  mainModel: string;
  fastModel: string;
  /** `low` | `medium` | `high` | `xhigh` | `max`. */
  effort: string;
  /**
   * True when the user has chosen nothing and these are the workspace defaults.
   * Not derivable from the values — a default and a deliberate pick of the same
   * model look identical — so the hub says which it is, and the screen can stop
   * presenting a default as though the user had selected it.
   */
  usingDefaults: boolean;
}

/* ── Change notification ─────────────────────────────────────────────────── */

let revision = 0;
const listeners = new Set<() => void>();

/** For `useSyncExternalStore`. */
export function subscribeModelPreferences(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** For `useSyncExternalStore` — changes whenever the preference might have. */
export function getModelPreferencesRevision(): number {
  return revision;
}

/** Announce a change every reader should act on. */
function modelPreferencesChanged(): void {
  revision += 1;
  for (const listener of listeners) listener();
}

/* ── Calls ───────────────────────────────────────────────────────────────── */

/** `GET /me/model-preferences`. Returns the configured defaults if none are saved. */
export const getModelPreferences = (): Promise<ModelPreferences> =>
  api.get<ModelPreferences>(PATH);

/**
 * `PUT /me/model-preferences`. The whole preference is sent together — the hub
 * validates it and returns the full new state, so callers render the hub's
 * answer rather than assuming their optimistic value was accepted.
 */
export const setModelPreferences = async (
  next: Omit<ModelPreferences, "usingDefaults">,
): Promise<ModelPreferences> => {
  const saved = await api.put<ModelPreferences>(PATH, next);
  modelPreferencesChanged();
  return saved;
};

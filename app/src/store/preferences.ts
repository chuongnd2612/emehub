// Workspace preferences — the Settings screen's Workspace defaults and
// Notifications.
//
// ## Why these are local
//
// **The hub has no preferences endpoint.** Nothing in the API stores a default
// provider, a default agent, a knowledge scope or a notification choice
// (checked against `/openapi.json`). Until it does, these live here, persisted to
// localStorage — the same mechanism `store/appearance.ts` already uses.
//
// That is a deliberate, stated compromise rather than a hidden one. They are
// **per-browser**, not per-workspace, so a colleague sees their own values and a
// new device starts from the defaults. The Settings screen says so on the card;
// see the hub-side issue for the endpoint that would make them shared.
//
// The alternative was worse in both directions: leaving them in screen state
// meant a Save button that saved nothing (a lying control), and inventing a
// `PUT /preferences` call would have failed against the real API.

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type DefaultProvider = "Azure DevOps" | "Jira" | "GitHub";
export type DefaultAgent = "Q-Agent" | "D-Agent" | "None";
export type KnowledgeScope = "Per project" | "Workspace";

/**
 * The saved values. Kept as one flat object so the Settings screen can diff a
 * draft against it with a single comparison rather than field by field.
 */
export interface Preferences {
  defProvider: DefaultProvider;
  defAgent: DefaultAgent;
  defScope: KnowledgeScope;
  /** Alert when a provider import fails or partially completes. */
  notifImport: boolean;
  /** Alert before a stored credential expires. */
  notifCred: boolean;
  /** Alert on every finished agent run. */
  notifRuns: boolean;
}

/** The prototype's defaults (on / on / off for the notifications). */
export const DEFAULT_PREFERENCES: Preferences = {
  defProvider: "Azure DevOps",
  defAgent: "Q-Agent",
  defScope: "Per project",
  notifImport: true,
  notifCred: true,
  notifRuns: false,
};

interface PreferencesState extends Preferences {
  /** Commit a whole draft. The Settings screen saves in bulk, never per field. */
  save: (next: Preferences) => void;
  reset: () => void;
}

export const usePreferences = create<PreferencesState>()(
  persist(
    (set) => ({
      ...DEFAULT_PREFERENCES,
      save: (next) => set({ ...next }),
      reset: () => set({ ...DEFAULT_PREFERENCES }),
    }),
    {
      name: "emehub.preferences",
      // Only the values — never the actions, and never anything else that lands
      // in the store later.
      partialize: (s): Preferences => ({
        defProvider: s.defProvider,
        defAgent: s.defAgent,
        defScope: s.defScope,
        notifImport: s.notifImport,
        notifCred: s.notifCred,
        notifRuns: s.notifRuns,
      }),
    },
  ),
);

/** The saved values as a plain object, for diffing a draft against. */
export const readPreferences = (s: PreferencesState): Preferences => ({
  defProvider: s.defProvider,
  defAgent: s.defAgent,
  defScope: s.defScope,
  notifImport: s.notifImport,
  notifCred: s.notifCred,
  notifRuns: s.notifRuns,
});

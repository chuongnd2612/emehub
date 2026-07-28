// Handoff › State Management › "Shell", minus everything that is navigation.
//
// `view`, `page` and `projectId` from the prototype are DELIBERATELY absent:
// the URL is the source of truth for navigation (CLAUDE.md › Frontend
// conventions). Intra-screen selection goes in query params, not here.

import { create } from "zustand";

/** Which 520px modal is open, or null. */
export type ModalKey =
  | "project"
  | "invite"
  | "knowledge"
  | "apiKey"
  | "integration"
  | "import"
  | null;

export interface UiState {
  /** Command palette (⌘K / Ctrl+K, or the header search button). */
  paletteOpen: boolean;
  paletteQuery: string;
  /** The open modal. */
  modal: ModalKey;
  /** Key of the single open dropdown — every dropdown closes when another opens. */
  dd: string | null;
  /** Key of the open drawer, or null. */
  drawer: string | null;
  /** Appearance popover in the header. */
  themeOpen: boolean;
  /** Claude credential popover in the header. */
  claudeOpen: boolean;

  setPaletteOpen: (open: boolean) => void;
  togglePalette: () => void;
  setPaletteQuery: (query: string) => void;
  setModal: (modal: ModalKey) => void;
  setDd: (dd: string | null) => void;
  toggleDd: (dd: string) => void;
  setDrawer: (drawer: string | null) => void;
  setThemeOpen: (open: boolean) => void;
  setClaudeOpen: (open: boolean) => void;
  /** Close every overlay — bound to Esc and to scrim clicks. */
  closeAll: () => void;
}

export const useUi = create<UiState>()((set) => ({
  paletteOpen: false,
  paletteQuery: "",
  modal: null,
  dd: null,
  drawer: null,
  themeOpen: false,
  claudeOpen: false,

  setPaletteOpen: (paletteOpen) => set({ paletteOpen, paletteQuery: "" }),
  togglePalette: () =>
    set((s) => ({ paletteOpen: !s.paletteOpen, paletteQuery: "" })),
  setPaletteQuery: (paletteQuery) => set({ paletteQuery }),
  setModal: (modal) => set({ modal, dd: null, themeOpen: false }),
  setDd: (dd) => set({ dd, themeOpen: false, claudeOpen: false }),
  toggleDd: (dd) =>
    set((s) => ({
      dd: s.dd === dd ? null : dd,
      themeOpen: false,
      claudeOpen: false,
    })),
  setDrawer: (drawer) => set({ drawer }),
  setThemeOpen: (themeOpen) => set({ themeOpen, dd: null, claudeOpen: false }),
  setClaudeOpen: (claudeOpen) => set({ claudeOpen, dd: null, themeOpen: false }),
  closeAll: () =>
    set({
      modal: null,
      dd: null,
      themeOpen: false,
      paletteOpen: false,
      drawer: null,
      claudeOpen: false,
    }),
}));

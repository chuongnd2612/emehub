// Handoff › State Management › "Appearance".
// Persisted to localStorage so the workspace looks the same on the next visit.
// This store holds appearance ONLY — navigation lives in the URL (CLAUDE.md).

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Mode = "dark" | "light";
export type Accent = "red" | "purple" | "cyan" | "steel";

/** The four brand accents, as offered by Settings › Appearance › Brand colour. */
export const ACCENTS: { key: Accent; label: string; hex: number }[] = [
  { key: "red", label: "EMESOFT Red", hex: 0xe1172b },
  { key: "purple", label: "Agent Purple", hex: 0x8b5cf6 },
  { key: "cyan", label: "Signal Cyan", hex: 0x22d3ee },
  { key: "steel", label: "Metallic Steel", hex: 0xb4becd },
];

export interface AppearanceState {
  mode: Mode;
  accent: Accent;
  /** Ambient bloom opacity, 0–100 step 5. */
  ambient: number;
  /** 3D constellation field on/off — tears down / re-creates the WebGL scene. */
  fx3d: boolean;
  /** Depth on hover — gates ALL pointer tilt. */
  tilt: boolean;
  setMode: (mode: Mode) => void;
  toggleMode: () => void;
  setAccent: (accent: Accent) => void;
  setAmbient: (ambient: number) => void;
  setFx3d: (fx3d: boolean) => void;
  setTilt: (tilt: boolean) => void;
}

export const useAppearance = create<AppearanceState>()(
  persist(
    (set) => ({
      mode: "dark",
      accent: "red",
      ambient: 85,
      fx3d: true,
      tilt: true,
      setMode: (mode) => set({ mode }),
      toggleMode: () =>
        set((s) => ({ mode: s.mode === "light" ? "dark" : "light" })),
      setAccent: (accent) => set({ accent }),
      setAmbient: (ambient) => set({ ambient }),
      setFx3d: (fx3d) => set({ fx3d }),
      setTilt: (tilt) => set({ tilt }),
    }),
    { name: "emehub.appearance" },
  ),
);

/** The three.js palette hex for the current accent (Handoff › 3D constellation). */
export function accentHex(accent: Accent): number {
  return ACCENTS.find((a) => a.key === accent)?.hex ?? 0xe1172b;
}

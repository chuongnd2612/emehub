// Handoff › Overlays › Toast — bottom-centre glass pill, `toastIn` entrance,
// a `ring`-pulsing 30px status ring, a `toastBar` countdown, auto-dismiss
// after 3200 ms. Kinds: ok | warn | info.

import { create } from "zustand";

export const TOAST_DURATION_MS = 3200;

export type ToastKind = "ok" | "warn" | "info";

export interface Toast {
  id: number;
  title: string;
  body: string;
  kind: ToastKind;
}

interface ToastState {
  toast: Toast | null;
  /** Show a toast. Only one is visible at a time — a new one replaces it. */
  push: (title: string, body: string, kind?: ToastKind) => void;
  dismiss: () => void;
}

let seq = 0;
let timer: ReturnType<typeof setTimeout> | undefined;

export const useToast = create<ToastState>()((set) => ({
  toast: null,
  push: (title, body, kind = "ok") => {
    if (timer) clearTimeout(timer);
    set({ toast: { id: ++seq, title, body, kind } });
    timer = setTimeout(() => set({ toast: null }), TOAST_DURATION_MS);
  },
  dismiss: () => {
    if (timer) clearTimeout(timer);
    set({ toast: null });
  },
}));

/** Imperative helper for non-component code (data layer callbacks etc). */
export const toast = (title: string, body: string, kind: ToastKind = "ok") =>
  useToast.getState().push(title, body, kind);

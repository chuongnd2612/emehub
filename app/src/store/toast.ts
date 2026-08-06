// Handoff › Overlays › Toast — bottom-centre glass pill, `toastIn` entrance,
// a `ring`-pulsing 30px status ring, a `toastBar` countdown, auto-dismiss
// after 3200 ms. Kinds: ok | warn | info.

import { create } from "zustand";

export const TOAST_DURATION_MS = 3200;

export type ToastKind = "ok" | "warn" | "info";

export interface Toast {
  id: number;
  title: string;
  /**
   * Second line. **Optional, and usually absent.** A toast says one short thing;
   * a body restating the title ("Key copied" / "<name> copied to clipboard") is
   * noise. Pass one only when it carries something the user cannot otherwise
   * see — a provider's own failure reason being the case that matters, since
   * that is the actionable half of the message.
   */
  body?: string;
  kind: ToastKind;
}

interface ToastState {
  toast: Toast | null;
  /**
   * Show a toast. Only one is visible at a time — a new one replaces it.
   *
   * `kind` comes before `body` because the overwhelmingly common call is a
   * one-liner (`push("Invitation sent")`, `push("Sync failed", "warn")`) and the
   * body is the exception. It also means the old `(title, body, kind)` order is
   * a *type* error rather than a silently mis-rendered toast.
   */
  push: (title: string, kind?: ToastKind, body?: string) => void;
  dismiss: () => void;
}

let seq = 0;
let timer: ReturnType<typeof setTimeout> | undefined;

export const useToast = create<ToastState>()((set) => ({
  toast: null,
  push: (title, kind = "ok", body) => {
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
export const toast = (title: string, kind: ToastKind = "ok", body?: string) =>
  useToast.getState().push(title, kind, body);

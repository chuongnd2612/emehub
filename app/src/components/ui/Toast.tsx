// Handoff › Overlays › Toast — "bottom-centre, left:50% + translateX(-50%),
// animation:toastIn .34s cubic-bezier(.2,.7,.3,1), glass pill with a 30px
// status ring (`ring` pulse), title + body, auto-dismiss after 3200 ms,
// kinds ok | warn | info."
//
// Portalled to document.body. The store (store/toast.ts) owns the 3200 ms
// timer; this component only renders the current toast.

import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { TOAST_DURATION_MS, useToast, type ToastKind } from "@/store/toast";
import { Icon, type IconName } from "./Icon";

const KIND_ICON: Record<ToastKind, IconName> = {
  ok: "check",
  warn: "alert",
  info: "bolt",
};

const KIND_RING: Record<ToastKind, string> = {
  ok: "bg-ok-tint text-ok",
  warn: "bg-warn-tint text-warn",
  info: "bg-info-tint text-info",
};

const KIND_BAR: Record<ToastKind, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  info: "bg-info",
};

/** Mount once, at the app root. Renders whatever the toast store holds. */
export function ToastHost() {
  const toast = useToast((s) => s.toast);
  const dismiss = useToast((s) => s.dismiss);
  if (!toast) return null;

  return createPortal(
    <div
      key={toast.id}
      role="status"
      aria-live="polite"
      onClick={dismiss}
      className={cn(
        "fixed bottom-7 left-1/2 z-[1200] flex w-[min(420px,calc(100vw-32px))] cursor-pointer",
        "animate-toast-in items-start gap-3 overflow-hidden rounded-card border border-bd2",
        "bg-pop px-4 py-3.5 shadow-pop",
      )}
    >
      <span
        className={cn(
          "relative flex size-[30px] shrink-0 items-center justify-center rounded-full",
          KIND_RING[toast.kind],
        )}
      >
        <span
          className={cn(
            "absolute inset-0 animate-ring rounded-full",
            KIND_RING[toast.kind],
          )}
        />
        <Icon name={KIND_ICON[toast.kind]} size={15} strokeWidth={2.4} />
      </span>

      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-extrabold text-txt">{toast.title}</div>
        <div className="mt-[3px] text-[12px] leading-[1.5] text-muted">
          {toast.body}
        </div>
      </div>

      {/* Countdown bar — `toastBar` scaleX(1) -> scaleX(0) over the lifetime. */}
      <span
        className={cn(
          "absolute inset-x-0 bottom-0 h-[2px] origin-left",
          KIND_BAR[toast.kind],
        )}
        style={{ animation: `toastBar ${TOAST_DURATION_MS}ms linear forwards` }}
      />
    </div>,
    document.body,
  );
}

export { useToast, toast } from "@/store/toast";
export type { Toast, ToastKind } from "@/store/toast";

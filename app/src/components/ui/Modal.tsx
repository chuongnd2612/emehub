// Handoff › Overlays › Modals ("520px, var(--pop), radius 20,
// animation:fadeInUp .25s") and 5. Import dialog ("580px wide, var(--pop),
// radius 22, box-shadow 0 40px 90px -20px #000, animation:scaleIn .22s; scrim
// rgba(6,6,10,.62) + blur(7px), animation:fadeIn .2s").
//
// Portalled to document.body (CLAUDE.md). Closes on scrim click and Esc.

import { useCallback, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { useEscape } from "@/hooks/useAnchoredPosition";
import { Button } from "./Button";
import { Icon } from "./Icon";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** One-line subtitle under the title. */
  subtitle?: ReactNode;
  /** Leading glyph tile in the header (34px provider glyph on the import dialog). */
  glyph?: ReactNode;
  /** Footer content. Typically a note on the left and the actions on the right. */
  footer?: ReactNode;
  /** `dialog` = 580px + scaleIn .22s. `modal` = 520px + fadeInUp .25s. */
  size?: "modal" | "dialog";
  children?: ReactNode;
  className?: string;
}

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  glyph,
  footer,
  size = "modal",
  children,
  className,
}: ModalProps) {
  const close = useCallback(() => onClose(), [onClose]);
  useEscape(open, close);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[1100] flex items-start justify-center overflow-y-auto py-[10vh]"
      role="presentation"
    >
      {/* Scrim — rgba(6,6,10,.62) + blur(7px). Not a token: the scrim is the
          same in both modes by design (it sits over the whole viewport). */}
      <div
        className="fixed inset-0 animate-fade-in bg-[rgba(6,6,10,.62)] backdrop-blur-[7px]"
        onClick={close}
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "relative flex w-full flex-col bg-pop",
          size === "dialog"
            ? "max-w-[580px] animate-scale-in-dialog rounded-card-lg shadow-dialog"
            : "max-w-[520px] animate-fade-in-up rounded-[20px] shadow-dialog",
          className,
        )}
      >
        <header className="flex items-center gap-3 border-b border-bd3 px-5 py-4">
          {glyph}
          <div className="min-w-0 flex-1">
            <div className="truncate text-[16px] font-extrabold tracking-[-.02em] text-txt">
              {title}
            </div>
            {subtitle && (
              <div className="mt-[3px] truncate text-[12px] text-faint">
                {subtitle}
              </div>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            aria-label="Close"
            onClick={close}
            icon={<Icon name="close" size={15} strokeWidth={2.4} />}
          />
        </header>

        <div className="flex flex-col gap-3.5 px-5 py-5">{children}</div>

        {footer && (
          <footer className="flex items-center gap-3 border-t border-bd3 px-5 py-4">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}

// NO DESIGN WAS SUPPLIED FOR THIS SCREEN.
//
// Derived from QAgent's `app/src/screens/auth/SignedOut.tsx` (a gradient logout
// tile, a reassuring line, a full-width "Sign back in") and restyled in
// EmeHub's token language.
//
// The `?reason=` variants are not QAgent's — they come from INTEGRATION.md §5,
// which makes the distinction a hard requirement: when the hub is unreachable
// "the error page must say *the hub is down*, not *you are logged out*".
//   (none)      you clicked Sign out
//   expired     your session ended or was revoked from another device
//   unreachable the hub could not be reached — this is NOT a logout
//
// Ungated on purpose: logout lands here while the store may still say "authed"
// and clears the session on mount. Wrapping it in `RedirectIfAuthed` would
// bounce you straight back into the app.

import { useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button, Icon, type IconName } from "@/components/ui";
import { useAuth } from "@/store/auth";

interface Variant {
  icon: IconName;
  title: string;
  body: string;
  cta: string;
  /** Rose treatment for the failure case, accent for a clean sign-out. */
  danger?: boolean;
}

const VARIANTS: Record<string, Variant> = {
  signedOut: {
    icon: "logout",
    title: "You are signed out",
    body: "Your session on this device has ended. Provider credentials stay encrypted in the hub — nothing was revoked.",
    cta: "Sign back in",
  },
  expired: {
    icon: "lock",
    title: "Your session ended",
    body: "The session expired or was revoked from another device. Sign in again to pick up where you left off.",
    cta: "Sign in again",
  },
  unreachable: {
    icon: "alert",
    title: "The hub is unreachable",
    body: "EmeHub could not be reached, so we cannot confirm your session. You have not been signed out — try again once the hub is back.",
    cta: "Try again",
    danger: true,
  },
};

export default function SignedOutScreen() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const reason = params.get("reason") ?? "";
  const variant = VARIANTS[reason] ?? VARIANTS.signedOut;

  // Finalise the sign-out HERE, once we are safely on a public route. Doing it
  // from the account screen instead would race the guards: `status` would flip
  // to "anon" and `RequireAuth` would redirect to /login before the navigation
  // to this screen commits.
  //   • signedOut → `logout()`: revokes the session server-side, clears the
  //     cookies, then clears local state. Never rejects.
  //   • expired   → `clear()`: the session is already gone; there is nothing to
  //     revoke and the call would only 401.
  //   • unreachable → neither. We have NOT signed you out (INTEGRATION.md §5).
  //
  // The latch is not optional: StrictMode runs this effect twice in dev, and a
  // second `POST /auth/logout` on an already-revoked session 401s. Observed
  // live before it was added.
  const done = useRef(false);
  useEffect(() => {
    if (done.current || reason === "unreachable") return;
    done.current = true;
    if (reason === "expired") useAuth.getState().clear();
    else void useAuth.getState().logout();
  }, [reason]);

  return (
    <AuthLayout>
      <div className="flex flex-col items-center gap-[9px] px-2 py-6 text-center">
        <span
          className={
            variant.danger
              ? "mb-2 flex size-[60px] items-center justify-center rounded-[19px] border border-danger/30 bg-danger-tint text-danger"
              : "animate-scale-in mb-2 flex size-[60px] items-center justify-center rounded-[19px] bg-accent-grad text-white shadow-primary"
          }
        >
          <Icon name={variant.icon} size={26} strokeWidth={2.2} />
        </span>

        <h1 className="m-0 text-[23px] leading-tight font-black tracking-[-.035em] text-txt">
          {variant.title}
        </h1>
        <p className="m-0 mb-4 max-w-[42ch] text-[12.5px] leading-[1.55] text-pretty text-muted">
          {variant.body}
        </p>

        <Button
          variant="primary"
          size="lg"
          className="w-full"
          onClick={() => {
            // "Try again" on the unreachable variant retries the last route
            // rather than asserting a logout that never happened.
            if (variant.danger) navigate(0);
            else navigate("/login");
          }}
        >
          {variant.cta}
        </Button>
      </div>
    </AuthLayout>
  );
}

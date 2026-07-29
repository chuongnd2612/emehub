// NO DESIGN WAS SUPPLIED FOR THIS SCREEN.
//
// Derived from QAgent's `app/src/screens/auth/ForgotPassword.tsx` (request
// form → "check your inbox" confirmation, with the dev-only token echo), then
// restyled in EmeHub's token language. QAgent folds the reset step into this
// same route behind `?token=`; here reset is its own URL (`/reset?token=`),
// because the URL is the source of truth for navigation and "I am setting a new
// password" is a different screen from "I forgot my password".
//
// The confirmation uses the handoff's empty-state recipe (40px glyph tile, a
// one-line explanation, a primary CTA) rather than inventing a new one.

import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AuthLayout } from "@/components/auth/AuthLayout";
import {
  AuthBackLink,
  AuthField,
  AuthHeading,
} from "@/components/auth/fields";
import { Button, EmptyState, Icon, Notice, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

interface RequestResetResponse {
  ok: boolean;
  /** Echoed outside production only — email delivery is not wired yet. */
  token: string | null;
}

export default function ForgotPasswordScreen() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const address = email.trim();
    if (pending || !address) return;
    setPending(true);
    setError(null);
    try {
      const res = await api.post<RequestResetResponse>("/auth/request-reset", {
        email: address,
      });
      setDevToken(res.token ?? null);
      setSent(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reach the hub. Try again in a moment.",
      );
    } finally {
      setPending(false);
    }
  };

  if (sent) {
    return (
      <AuthLayout>
        <EmptyState
          icon="mail"
          title="Check your inbox"
          body={`If ${email.trim()} has an account, a reset link is on its way. The link expires shortly — request another if it does.`}
          action={
            <Button variant="primary" onClick={() => navigate("/login")}>
              Back to sign in
            </Button>
          }
        />

        {/* The hub echoes the token outside production because email delivery
            is a stub (`api/app/routers/auth.py › request_reset`). Surfaced as a
            labelled development affordance, never as normal product copy. */}
        {devToken && (
          <Notice tone="info" className="mt-1">
            Email delivery is not wired up on this environment, so the hub
            returned the reset token directly.{" "}
            <Link
              to={`/reset?token=${encodeURIComponent(devToken)}`}
              className="font-bold underline underline-offset-2"
            >
              Open the reset screen
            </Link>
            .
          </Notice>
        )}
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <AuthBackLink label="Back to sign in" onClick={() => navigate("/login")} />
      <AuthHeading
        title="Reset your password"
        subtitle="Enter your work email and we will send a link to set a new one."
      />

      <form onSubmit={submit} noValidate className="flex flex-col gap-3.5">
        <AuthField
          label="WORK EMAIL"
          type="email"
          autoComplete="email"
          required
          autoFocus
          icon={<Icon name="mail" size={15} strokeWidth={2.2} />}
          placeholder="name@emesoft.net"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        {error && <Notice tone="danger">{error}</Notice>}

        <Button
          type="submit"
          variant="primary"
          size="lg"
          disabled={pending || !email.trim()}
          className="mt-0.5 w-full"
          icon={pending ? <Spinner size={16} speed="upload" /> : undefined}
        >
          {pending ? "Sending…" : "Send reset link"}
        </Button>
      </form>
    </AuthLayout>
  );
}

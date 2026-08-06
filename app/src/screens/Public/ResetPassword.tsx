// NO DESIGN WAS SUPPLIED FOR THIS SCREEN.
//
// Derived from the reset half of QAgent's
// `app/src/screens/auth/ForgotPassword.tsx` (`?token=` → new password +
// confirm → `POST /auth/reset` → back to sign in), split onto its own route
// and restyled in EmeHub's token language.
//
// This is also the screen an invited teammate lands on: `POST
// /auth/users/invite` creates the account with an unusable password and hands
// back a reset token, so redeeming an invitation and resetting a forgotten
// password are literally the same request.

import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AuthLayout } from "@/components/auth/AuthLayout";
import { AuthHeading, AuthPasswordField } from "@/components/auth/fields";
import { Button, EmptyState, Notice, Spinner, toast } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

/** The hub hashes whatever it is given; this is the client-side floor. */
const MIN_LENGTH = 12;

export default function ResetPasswordScreen() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token");

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A missing token is not an error state to recover from in place — the link
  // is malformed, so say that and send them back to the start.
  if (!token) {
    return (
      <AuthLayout>
        <EmptyState
          icon="alert"
          title="This reset link is incomplete"
          body="The link is missing its token, so we cannot tell which account to reset. Request a fresh one and use the newest email."
          action={
            <Button variant="primary" onClick={() => navigate("/forgot")}>
              Request a new link
            </Button>
          }
        />
      </AuthLayout>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (pending) return;
    if (password.length < MIN_LENGTH) {
      setError(`Use at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await api.post("/auth/reset", { token, password });
      toast("Password updated");
      navigate("/login", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reach the hub. Try again in a moment.",
      );
      setPending(false);
    }
  };

  return (
    <AuthLayout>
      <AuthHeading
        title="Choose a new password"
        subtitle={`At least ${MIN_LENGTH} characters. Setting it signs out every device currently using this account.`}
      />

      <form onSubmit={submit} noValidate className="flex flex-col gap-3.5">
        <AuthPasswordField
          label="NEW PASSWORD"
          autoComplete="new-password"
          required
          autoFocus
          placeholder="••••••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <AuthPasswordField
          label="CONFIRM NEW PASSWORD"
          autoComplete="new-password"
          required
          placeholder="••••••••••••"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />

        {error && <Notice tone="danger">{error}</Notice>}

        <Button
          type="submit"
          variant="primary"
          size="lg"
          disabled={pending}
          className="mt-0.5 w-full"
          icon={pending ? <Spinner size={16} speed="upload" /> : undefined}
        >
          {pending ? "Saving…" : "Set password and sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}

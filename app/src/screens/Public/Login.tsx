// NO DESIGN WAS SUPPLIED FOR THIS SCREEN.
//
// The handoff assumes an authenticated user — there is no sign-in screen in
// `design/design_handoff_emehub/`. Structure and behaviour are derived from
// QAgent's `app/src/screens/auth/Login.tsx` (two-step email/password → TOTP
// inside a shared layout, MFA discriminated on a truthy `mfaRequired`), then
// restyled entirely in EmeHub's token language via `components/auth/`.
//
// Deliberately absent, both because they have no design and no endpoint: SSO
// buttons, an "OR" divider, and a sign-up link. Accounts are admin-provisioned
// (`POST /auth/users/invite`), so there is nothing to sign up for.

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import {
  AuthBackLink,
  AuthCheckbox,
  AuthField,
  AuthHeading,
  AuthPasswordField,
  CodeField,
} from "@/components/auth/fields";
import { AuthLayout, AuthLoader } from "@/components/auth/AuthLayout";
import { Button, Icon, Notice, Spinner } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/store/auth";

/** Never render a raw exception at a signed-out visitor. */
const message = (error: unknown, fallback: string): string =>
  error instanceof ApiError && typeof error.message === "string"
    ? error.message
    : fallback;

export default function LoginScreen() {
  const navigate = useNavigate();
  const login = useAuth((s) => s.login);
  const loginMfa = useAuth((s) => s.loginMfa);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);

  // Set once the hub answers with an MFA challenge; until then we are on step 1.
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");

  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [entering, setEntering] = useState(false);

  const enter = () => {
    setEntering(true);
    navigate("/app", { replace: true });
  };

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const outcome = await login({ email: email.trim(), password, remember });
      if (outcome.kind === "mfa") {
        setMfaToken(outcome.mfaToken);
        setPending(false);
        return;
      }
      enter();
    } catch (err) {
      setError(message(err, "Could not reach the hub. Try again in a moment."));
      setPending(false);
    }
  };

  const submitCode = async (e: FormEvent) => {
    e.preventDefault();
    if (pending || !mfaToken) return;
    setPending(true);
    setError(null);
    try {
      await loginMfa({ mfaToken, code });
      enter();
    } catch (err) {
      setError(message(err, "That code was not accepted. Try the next one."));
      setPending(false);
    }
  };

  if (entering) return <AuthLoader label="Opening your workspace" />;

  if (mfaToken) {
    return (
      <AuthLayout>
        <AuthBackLink
          label="Use a different account"
          onClick={() => {
            setMfaToken(null);
            setCode("");
            setError(null);
          }}
        />
        <AuthHeading
          title="Two-factor required"
          subtitle="Enter the six-digit code from your authenticator app."
        />

        <form onSubmit={submitCode} className="flex flex-col gap-3.5">
          <CodeField
            label="VERIFICATION CODE"
            value={code}
            onChange={setCode}
            autoFocus
            disabled={pending}
          />

          {error && <Notice tone="danger">{error}</Notice>}

          <Button
            type="submit"
            variant="primary"
            size="lg"
            disabled={pending || code.length < 6}
            className="mt-0.5 w-full"
            icon={pending ? <Spinner size={16} speed="upload" /> : undefined}
          >
            {pending ? "Verifying…" : "Verify and sign in"}
          </Button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <AuthHeading
        title="Sign in to EmeHub"
        subtitle="One identity for Q-Agent, D-Agent and every connected provider."
      />

      <form onSubmit={submitPassword} className="flex flex-col gap-3.5">
        <AuthField
          label="WORK EMAIL"
          type="email"
          autoComplete="username"
          required
          autoFocus
          icon={<Icon name="mail" size={15} strokeWidth={2.2} />}
          placeholder="name@emesoft.net"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <AuthPasswordField
          label="PASSWORD"
          autoComplete="current-password"
          required
          placeholder="••••••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          labelAction={
            <button
              type="button"
              data-surface
              onClick={() => navigate("/forgot")}
              className="cursor-pointer bg-transparent p-0 text-[11px] font-bold text-ps-text hover:text-p"
            >
              Forgot password?
            </button>
          }
        />

        <AuthCheckbox checked={remember} onChange={setRemember}>
          Keep me signed in on this device
        </AuthCheckbox>

        {error && <Notice tone="danger">{error}</Notice>}

        <Button
          type="submit"
          variant="primary"
          size="lg"
          disabled={pending}
          className="mt-0.5 w-full"
          icon={pending ? <Spinner size={16} speed="upload" /> : undefined}
        >
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="m-0 mt-[22px] text-center text-[12px] leading-[1.5] text-faint">
        Accounts are provisioned by a workspace admin. Ask one to invite you.
      </p>
    </AuthLayout>
  );
}

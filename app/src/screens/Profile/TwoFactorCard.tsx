// NO DESIGN WAS SUPPLIED FOR THIS SCREEN.
//
// Derived from QAgent's `app/src/screens/auth/profile/TwoFactorModal.tsx`
// (setup → copy the secret → confirm a code → enable; disable behind a code or
// the password) and restyled onto EmeHub's tokens. Rendered inline as a card
// rather than a modal because it is the third section of an account page, not
// an interruption.
//
// One deliberate omission: QAgent renders a QR code via `qrcode.react`. EmeHub
// has no such dependency and adding one is out of scope for this slice, so the
// secret and the otpauth URI are offered as copyable values with a note. Adding
// the QR later is a drop-in.
//
// SECURITY (CLAUDE.md › "Never log or return a secret"): the TOTP secret from
// `POST /auth/2fa/setup` lives in component state only, is never persisted or
// logged, and is dropped the moment enrolment completes or is abandoned.

import { useState } from "react";

import {
  Button,
  GlassCard,
  Icon,
  Notice,
  Pill,
  Spinner,
  toast,
} from "@/components/ui";
import { CodeField } from "@/components/auth/fields";
import { Hairline, SettingRow } from "@/screens/Settings/SettingRow";
import { disableTotp, enableTotp, startTotpSetup, type TotpSetup } from "@/data";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useAuth } from "@/store/auth";

const reason = (error: unknown, fallback: string): string =>
  error instanceof ApiError ? error.message : fallback;

/** A copyable value — the secret and the otpauth URI both use it. */
function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      toast("Could not copy", "Select the value and copy it by hand", "warn");
    }
  };
  return (
    <div className="flex flex-col gap-[7px]">
      <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
        {label}
      </span>
      <div className="flex items-center gap-2.5 rounded-control-lg border border-bd2 bg-card3 py-2 pr-2 pl-3.5">
        <code className="min-w-0 flex-1 overflow-x-auto font-mono text-[12px] whitespace-nowrap text-txt2">
          {value}
        </code>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void copy()}
          icon={
            <Icon
              name={copied ? "check" : "copy"}
              size={13}
              strokeWidth={2.2}
            />
          }
        >
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

export function TwoFactorCard() {
  const user = useAuth((s) => s.user);
  const refreshUser = useAuth((s) => s.refreshUser);
  const enabled = Boolean(user?.totpEnabled);

  /** Enrolment material. Non-null == mid-setup. */
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [disarming, setDisarming] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setSetup(null);
    setDisarming(false);
    setCode("");
    setError(null);
  };

  const begin = async () => {
    setPreparing(true);
    setError(null);
    try {
      setSetup(await startTotpSetup());
    } catch (err) {
      setError(reason(err, "The hub did not respond."));
    } finally {
      setPreparing(false);
    }
  };

  const confirm = async () => {
    if (busy || code.length < 6) return;
    setBusy(true);
    setError(null);
    try {
      await enableTotp(code);
      reset();
      await refreshUser();
      toast(
        "Two-factor enabled",
        "You will be asked for a code the next time you sign in",
        "ok",
      );
    } catch (err) {
      setError(reason(err, "That code was not accepted. Try the next one."));
    } finally {
      setBusy(false);
    }
  };

  const turnOff = async () => {
    if (busy || code.length < 6) return;
    setBusy(true);
    setError(null);
    try {
      await disableTotp({ code });
      reset();
      await refreshUser();
      toast(
        "Two-factor disabled",
        "Sign-in now needs your password only",
        "warn",
      );
    } catch (err) {
      setError(reason(err, "That code was not accepted. Try the next one."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <GlassCard className="flex flex-col gap-[14px] p-[22px]">
      <SettingRow
        label="Two-factor authentication"
        description="A six-digit code from an authenticator app, on top of your password."
      >
        <Pill tone={enabled ? "ok" : "neutral"} size="sm">
          {enabled ? "Enabled" : "Not enabled"}
        </Pill>
        {enabled ? (
          <Button
            variant="destructive"
            disabled={disarming}
            onClick={() => {
              reset();
              setDisarming(true);
            }}
          >
            Disable
          </Button>
        ) : (
          <Button
            variant="primary"
            disabled={preparing || Boolean(setup)}
            onClick={() => void begin()}
            icon={preparing ? <Spinner size={14} speed="upload" /> : undefined}
          >
            {preparing ? "Preparing…" : "Set up"}
          </Button>
        )}
      </SettingRow>

      {(setup || disarming) && <Hairline />}

      {setup && (
        <div className={cn("flex flex-col gap-[14px]")}>
          <Notice tone="warn">
            Store the secret in your password manager before you confirm. It is
            shown once and the hub will not return it again.
          </Notice>

          <CopyRow label="SECRET KEY" value={setup.secret} />
          <CopyRow label="OTPAUTH URI" value={setup.otpauthUri} />

          <p className="m-0 text-[12px] leading-[1.5] text-muted">
            Add either value to your authenticator app, then enter the code it
            shows to finish enrolment.
          </p>

          <CodeField
            label="VERIFICATION CODE"
            value={code}
            onChange={setCode}
            autoFocus
            disabled={busy}
          />

          {error && <Notice tone="danger">{error}</Notice>}

          <div className="flex items-center gap-2.5">
            <Button variant="ghost" disabled={busy} onClick={reset}>
              Cancel
            </Button>
            <Button
              variant="primary"
              className="ml-auto"
              disabled={busy || code.length < 6}
              onClick={() => void confirm()}
              icon={busy ? <Spinner size={14} speed="upload" /> : undefined}
            >
              {busy ? "Verifying…" : "Enable two-factor"}
            </Button>
          </div>
        </div>
      )}

      {disarming && (
        <div className="flex flex-col gap-[14px]">
          <Notice tone="warn">
            Turning two-factor off leaves your password as the only thing
            between an attacker and your provider credentials.
          </Notice>

          <CodeField
            label="CURRENT CODE"
            value={code}
            onChange={setCode}
            autoFocus
            disabled={busy}
          />

          {error && <Notice tone="danger">{error}</Notice>}

          <div className="flex items-center gap-2.5">
            <Button variant="ghost" disabled={busy} onClick={reset}>
              Keep it on
            </Button>
            <Button
              variant="destructive"
              className="ml-auto"
              disabled={busy || code.length < 6}
              onClick={() => void turnOff()}
              icon={busy ? <Spinner size={14} speed="upload" /> : undefined}
            >
              {busy ? "Disabling…" : "Disable two-factor"}
            </Button>
          </div>
        </div>
      )}

      {!setup && !disarming && error && (
        <Notice tone="danger">{error}</Notice>
      )}
    </GlassCard>
  );
}

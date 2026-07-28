// Handoff § 7 › Single sign-on — "SSO card (toggle, entity id / ACS URL /
// verified domain / certificate meta, MFA toggle) + session policy + a
// `barGrow`-animated recent-sign-ins chart".

import { useState } from "react";
import { GlassCard, Toggle } from "@/components/ui";
import { cn } from "@/lib/cn";

/**
 * Static SSO configuration copy from the prototype. There is no
 * `GET /api/auth/sso` in the data layer yet, so the card's metadata lives here
 * rather than behind an invented endpoint.
 */
const SSO_META = [
  { label: "ENTITY ID", value: "urn:emehub:emesoft", mono: true, ok: false },
  { label: "ACS URL", value: "hub.emesoft.net/sso/acs", mono: true, ok: false },
  { label: "VERIFIED DOMAIN", value: "emesoft.net", mono: false, ok: false },
  { label: "CERTIFICATE", value: "Valid until Apr 2027", mono: false, ok: true },
] as const;

const SESSION_POLICY = [
  "Idle timeout after 8 hours",
  "Absolute expiry after 30 days",
  "Re-auth required for credential changes",
] as const;

/**
 * Recent sign-ins, last 7 days, as a percentage of the tallest bar. The final
 * bar is today-so-far and renders in the neutral hairline colour.
 */
const SIGN_INS: readonly { height: number; partial?: boolean }[] = [
  { height: 52 },
  { height: 74 },
  { height: 61 },
  { height: 88 },
  { height: 70 },
  { height: 96 },
  { height: 44, partial: true },
];

export function SsoPanel() {
  const [ssoOn, setSsoOn] = useState(true);
  const [mfaOn, setMfaOn] = useState(true);

  return (
    <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-3.5">
      <GlassCard className="flex flex-col gap-4 p-[22px]">
        <div className="flex items-center gap-3.5">
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
              Single sign-on
            </div>
            <div className="mt-1 text-[12.5px] leading-[1.5] text-muted">
              SAML 2.0 via Microsoft Entra ID. Enforced for all @emesoft.net
              accounts.
            </div>
          </div>
          <span className="w-7 text-right text-[11.5px] font-bold text-muted">
            {ssoOn ? "On" : "Off"}
          </span>
          <Toggle
            checked={ssoOn}
            onChange={setSsoOn}
            aria-label="Single sign-on"
          />
        </div>

        <div className="grid grid-cols-2 gap-2.5">
          {SSO_META.map((m) => (
            <div
              key={m.label}
              className="rounded-[13px] border border-bd3 bg-inset px-[15px] py-[13px]"
            >
              <div className="text-[9.5px] font-bold tracking-[.1em] text-label">
                {m.label}
              </div>
              <div
                className={cn(
                  "mt-[5px] truncate",
                  m.mono ? "font-mono text-[11.5px]" : "text-[12px]",
                  m.ok ? "text-ok" : "text-txt2",
                )}
              >
                {m.value}
              </div>
            </div>
          ))}
        </div>

        <div className="h-px bg-bd3" />

        <div className="flex items-center gap-3.5">
          <div className="min-w-0 flex-1">
            <div className="text-[13.5px] font-bold text-txt">
              Require multi-factor authentication
            </div>
            <div className="mt-[3px] text-[12px] leading-[1.5] text-muted">
              Applies to admins and owners even when SSO is bypassed.
            </div>
          </div>
          <span className="w-7 text-right text-[11.5px] font-bold text-muted">
            {mfaOn ? "On" : "Off"}
          </span>
          <Toggle
            checked={mfaOn}
            onChange={setMfaOn}
            aria-label="Require multi-factor authentication"
          />
        </div>
      </GlassCard>

      <div className="flex flex-col gap-3.5">
        <GlassCard className="p-5">
          <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
            Session policy
          </div>
          <div className="mt-3.5 flex flex-col gap-[11px]">
            {SESSION_POLICY.map((line) => (
              <div
                key={line}
                className="flex items-center gap-2.5 text-[12.5px] text-txt3"
              >
                <span className="size-[6px] shrink-0 rounded-full bg-pl" />
                {line}
              </div>
            ))}
          </div>
        </GlassCard>

        <GlassCard className="p-5">
          <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
            Recent sign-ins
          </div>
          {/* `barGrow` scaleY(.04) → scaleY(1), staggered. Bar height and the
              stagger delay are computed values — the inline-style exemption. */}
          <div className="mt-4 flex h-[56px] items-end gap-[5px]">
            {SIGN_INS.map((bar, i) => (
              <span
                key={i}
                className={cn(
                  "animate-bar-grow flex-1 origin-bottom rounded-[4px]",
                  bar.partial
                    ? "bg-bd2"
                    : "bg-[linear-gradient(180deg,var(--pl),var(--p))]",
                )}
                style={{
                  height: `${bar.height}%`,
                  animationDelay: `${i * 55}ms`,
                }}
              />
            ))}
          </div>
          <div className="mt-2.5 text-[11px] text-label">
            Last 7 days · 41 successful, 0 blocked
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

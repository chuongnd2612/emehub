// Handoff § 7 › Login providers.
//
// The handoff shows four provider rows with toggles — Microsoft Entra ID
// ("Primary provider · 6 of 6 members"), Google Workspace, GitHub, and email +
// password marked "Disabled by workspace policy". All of it was invented, and the
// last row had it backwards: email and password is the only method that works.
//
// The hub authenticates one way (`POST /auth/login` against an Argon2 hash, with
// optional TOTP) and has no federation of any kind — no endpoint, no model, no
// config. So this panel states what is true and offers no toggle: there is
// nothing to switch it to, and a control that changes nothing is a lying control
// (the same rule `data/tickets.ts` applies to filter pills).
//
// What it *does* surface is the real second factor, from `/auth/me`. That is a
// genuine part of how sign-in works here, and the one thing on this screen a user
// can act on.

import { GlassCard, Glyph, Icon, Pill } from "@/components/ui";
import { useAuth } from "@/store/auth";

export function LoginProvidersPanel() {
  const user = useAuth((s) => s.user);
  const totpOn = Boolean(user?.totpEnabled);

  return (
    <GlassCard radius="panel" className="flex flex-col gap-4 p-5">
      <div>
        <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
          Sign-in methods
        </div>
        <p className="mt-1 mb-0 text-[12.5px] leading-[1.55] text-muted">
          EmeHub authenticates with an email address and a password, and hands
          that identity to every agent in the suite. Federated sign-in is not
          available.
        </p>
      </div>

      <div className="flex items-center gap-3.5 rounded-card border border-bd2 bg-card3 p-4">
        <Glyph
          size={34}
          fill="neutral"
          icon={<Icon name="key" size={16} strokeWidth={2.2} />}
        />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-extrabold tracking-[-.01em] text-txt">
            Email and password
          </div>
          <div className="mt-[3px] truncate text-[12px] text-muted">
            The only sign-in method this workspace supports
          </div>
        </div>
        {/* No toggle. Turning off the only way in would lock every member out,
            so this is stated rather than offered. */}
        <Pill tone="ok" size="sm">
          Active
        </Pill>
      </div>

      <div className="flex items-center gap-3.5 rounded-card border border-bd2 bg-card3 p-4">
        <Glyph
          size={34}
          fill="neutral"
          icon={<Icon name="lock" size={16} strokeWidth={2.2} />}
        />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-extrabold tracking-[-.01em] text-txt">
            Two-factor authentication
          </div>
          <div className="mt-[3px] text-[12px] text-muted">
            {totpOn
              ? "A code from your authenticator app is required at sign-in"
              : "Add an authenticator app from your profile to require a code"}
          </div>
        </div>
        {/* Real state, from /auth/me. Enrolment stays on the profile screen: it
            needs the QR secret and a verification code, so duplicating the flow
            here would mean two places to keep correct. */}
        <Pill tone={totpOn ? "ok" : "neutral"} size="sm">
          {totpOn ? "Enabled" : "Not enrolled"}
        </Pill>
      </div>
    </GlassCard>
  );
}

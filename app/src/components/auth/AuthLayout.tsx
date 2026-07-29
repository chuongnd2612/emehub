// NO DESIGN WAS SUPPLIED FOR THE UNAUTHENTICATED SCREENS.
//
// `design/design_handoff_emehub/` covers the landing view, eight in-app pages
// and the overlays. There is no sign-in, forgot-password, reset or signed-out
// screen anywhere in it, and the prototype contains no "Sign in" copy at all —
// `EmeHub.dc.html` models "Email and password" only as a *login provider that
// is off by policy*.
//
// Structure and behaviour are therefore derived from QAgent's
// `app/src/components/auth/AuthLayout.tsx` (split brand panel + form panel, the
// post-login redirect loader) and restyled entirely in EmeHub's token language:
//
//   • The ambient stack, not QAgent's two violet glows — this reuses the
//     shell's own `BackgroundStack` (flat --bg + the two --pt/--bloom2 blooms
//     at 660/740px, glowPulse 9s/11s) so a signed-out visitor sees the same
//     surface as a signed-in one, WebGL constellation included (mounted once
//     above the router in main.tsx, so it is already behind us here).
//   • The handoff's glass card recipe for the form panel: var(--card),
//     blur(22px), 1px var(--bd), radius 22, padding 26, fadeInUp .38s.
//   • Accent gradient primary (--pg + 0 8px 20px -6px var(--pglow)) via the
//     shared `Button` primitive, Satoshi/JetBrains Mono, four accents and both
//     modes — nothing here hard-codes a colour.
//   • The brand lockup is the sidebar's, verbatim: accent tile + spark glyph +
//     "Eme" / silver "Hub" + the AI OPERATING CENTER tracked label.

import type { ReactNode } from "react";

import { BackgroundStack } from "@/components/shell";
import { GlassCard, Icon } from "@/components/ui";
import { cn } from "@/lib/cn";

/** The product lockup from the sidebar, reused so the two never drift. */
export function BrandLockup({ size = "md" }: { size?: "md" | "lg" }) {
  const large = size === "lg";
  return (
    <div className="flex items-center gap-[11px]">
      <span
        className={cn(
          "flex shrink-0 items-center justify-center rounded-[12px]",
          "bg-accent-grad shadow-[0_6px_18px_-4px_var(--pglow)]",
          large ? "size-11" : "size-9",
        )}
      >
        <Icon
          name="spark"
          size={large ? 23 : 19}
          strokeWidth={2.2}
          className="text-white"
        />
      </span>
      <div className="min-w-0">
        <div
          className={cn(
            "leading-none font-black tracking-[-.03em] text-txt",
            large ? "text-[21px]" : "text-[17px]",
          )}
        >
          Eme<span className="text-silver">Hub</span>
        </div>
        <div className="mt-[3px] text-[9px] font-bold tracking-[.12em] text-muted">
          AI OPERATING CENTER
        </div>
      </div>
    </div>
  );
}

/** The three proof points beside the form. Copy is ours — see the header. */
const BRAND_POINTS = [
  "One identity across Q-Agent and D-Agent",
  "Provider credentials encrypted at rest, never handed to an agent",
  "Every sign-in and credential change is audited",
] as const;

export interface AuthLayoutProps {
  children: ReactNode;
}

/**
 * Full-screen shell for the public auth routes. Renders OUTSIDE `AppLayout` —
 * these are top-level routes with no sidebar and no page header — so it owns
 * the background stack itself.
 */
export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="fixed inset-0 overflow-y-auto">
      <BackgroundStack />

      <div className="relative z-[2] flex min-h-full items-stretch gap-3.5 p-3.5">
        {/* Brand panel — hidden below 1024px, where the sidebar would also
            collapse. Mobile layouts are not designed (CLAUDE.md). */}
        <aside
          className={cn(
            "glass-panel relative hidden flex-1 flex-col justify-between overflow-hidden",
            "rounded-panel px-[50px] py-[54px] shadow-panel lg:flex",
          )}
        >
          <BrandLockup size="lg" />

          <div className="max-w-[440px]">
            <h1 className="m-0 mb-4 text-[34px] leading-[1.15] font-black tracking-[-.035em] text-balance text-txt">
              The source of truth for every EMESOFT agent
            </h1>
            <p className="m-0 mb-[26px] text-[14.5px] leading-[1.6] text-pretty text-txt4">
              Identity, credentials and shared configuration live here. The
              agents ask the hub — they never hold your provider tokens.
            </p>
            <div className="flex flex-col gap-[13px]">
              {BRAND_POINTS.map((point) => (
                <div key={point} className="flex items-start gap-[11px]">
                  <span className="mt-px flex size-[22px] shrink-0 items-center justify-center rounded-[7px] bg-ok-tint text-ok">
                    <Icon name="check" size={13} strokeWidth={3} />
                  </span>
                  <span className="text-[13.5px] font-medium text-txt3">
                    {point}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-[9px] text-[12px] text-muted">
            <span className="size-[7px] shrink-0 animate-pulse-dot rounded-full bg-ok shadow-[0_0_8px_var(--ok)]" />
            {/* No SAML: the Authentication screen's SSO card is a stub and the
                hub has no IdP integration. Claiming it on the sign-in screen
                would be a security claim the product cannot honour. The three
                below are all real — separate signing and encryption keys
                (ADR 0005), Argon2 hashing, and an audit row per sign-in. */}
            Two-key encryption · Argon2 hashing · audited access
          </div>
        </aside>

        {/* Form panel. */}
        <main className="flex w-full shrink-0 items-center justify-center px-[30px] py-10 lg:w-[min(560px,46vw)]">
          <GlassCard
            radius="panel"
            className="animate-fade-in-up w-full max-w-[420px] p-[26px]"
          >
            <div className="mb-6 lg:hidden">
              <BrandLockup />
            </div>
            {children}
          </GlassCard>
        </main>
      </div>
    </div>
  );
}

/**
 * Full-screen transition shown while the session bootstraps — the guards render
 * it instead of flashing the login screen at someone who is already signed in.
 *
 * Derived from QAgent's `RedirectLoader`, restyled: the accent tile from the
 * lockup, `ring 1.6s ease-out infinite` expanding rings (the toast ring
 * keyframe, reused as the handoff's only expanding-ring motion) and the
 * ambient stack behind it.
 */
export function AuthLoader({ label = "Restoring your session" }: { label?: string }) {
  return (
    <div className="fixed inset-0 overflow-hidden">
      <BackgroundStack />

      <div className="animate-fade-in relative z-[2] flex h-full flex-col items-center justify-center gap-[34px]">
        <div className="relative flex size-[132px] items-center justify-center">
          {/* Two staggered rings. The delay is a computed value per ring — the
              documented inline-style exemption. */}
          {[0, 800].map((delay) => (
            <span
              key={delay}
              aria-hidden
              className="absolute inset-0 animate-ring rounded-full border-[1.5px] border-pb"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
          <span className="relative flex size-16 items-center justify-center rounded-[20px] bg-accent-grad shadow-[0_0_44px_-4px_var(--pglow)]">
            <Icon name="spark" size={30} strokeWidth={2.2} className="text-white" />
          </span>
        </div>

        <div className="text-center">
          <div className="text-[21px] font-black tracking-[-.03em] text-txt">
            Eme<span className="text-silver">Hub</span>
          </div>
          <div
            role="status"
            aria-live="polite"
            className="mt-1.5 text-[12.5px] tracking-[.03em] text-muted"
          >
            {label}
          </div>
        </div>
      </div>
    </div>
  );
}

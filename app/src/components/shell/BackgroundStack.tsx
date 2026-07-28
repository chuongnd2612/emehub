// Handoff § 0. App shell › Background stack — four fixed, inset-0 layers:
//   z0  flat var(--bg)
//   z1  the WebGL constellation container — NOT rendered here. `<Constellation>`
//       is mounted once above the router (main.tsx) and owns its own container,
//       because the field also has to survive the landing view, which has no
//       app shell. It prepends that container to <body>, so it precedes these
//       blooms in DOM order and paints beneath them, as the handoff stacks it.
//   z1  bloom A — 660x660 at top:-16% left:-8%, radial var(--pt), blur(34px),
//       glowPulse 9s
//   z1  bloom B — 740x740 at bottom:-22% right:-6%, radial var(--bloom2),
//       blur(34px), glowPulse 11s with a 1s delay
//
// Bloom opacity is the *Ambient bloom* setting (0–100) — a genuinely computed
// value, which is the documented exception to the no-inline-styles rule.

import { useAppearance } from "@/store/appearance";

export function BackgroundStack() {
  const ambient = useAppearance((s) => s.ambient);
  const glow = { opacity: ambient / 100 };

  return (
    <>
      <div className="fixed inset-0 z-0 bg-bg" />

      <div
        aria-hidden
        className={
          "pointer-events-none fixed top-[-16%] left-[-8%] z-[1] size-[660px] rounded-full " +
          "bg-[radial-gradient(circle,var(--pt),transparent_62%)] blur-[34px] animate-glow-pulse"
        }
        style={glow}
      />

      <div
        aria-hidden
        className={
          "pointer-events-none fixed right-[-6%] bottom-[-22%] z-[1] size-[740px] rounded-full " +
          "bg-[radial-gradient(circle,var(--bloom2),transparent_62%)] blur-[34px] animate-glow-pulse " +
          "[animation-delay:1s] [animation-duration:11s]"
        }
        style={glow}
      />
    </>
  );
}

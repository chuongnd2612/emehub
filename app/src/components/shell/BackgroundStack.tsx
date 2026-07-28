// Handoff § 0. App shell › Background stack — four fixed, inset-0 layers:
//   z0  flat var(--bg)
//   z1  the WebGL constellation container (filled by the 3D-field agent)
//   z1  bloom A — 660x660 at top:-16% left:-8%, radial var(--pt), blur(34px),
//       glowPulse 9s
//   z1  bloom B — 740x740 at bottom:-22% right:-6%, radial var(--bloom2),
//       blur(34px), glowPulse 11s with a 1s delay
//
// Bloom opacity is the *Ambient bloom* setting (0–100) — a genuinely computed
// value, which is the documented exception to the no-inline-styles rule.

import { useAppearance } from "@/store/appearance";

/**
 * Stable mount point for the three.js renderer. The constellation agent looks
 * this element up by id; nothing else may reparent or remove it.
 */
export const CONSTELLATION_ROOT_ID = "constellation-root";

export function BackgroundStack() {
  const ambient = useAppearance((s) => s.ambient);
  const glow = { opacity: ambient / 100 };

  return (
    <>
      <div className="fixed inset-0 z-0 bg-bg" />

      <div
        id={CONSTELLATION_ROOT_ID}
        className="pointer-events-none fixed inset-0 z-[1]"
      />

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

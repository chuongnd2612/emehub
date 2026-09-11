// ADR 0012 › "WebGL orb". Lifecycle only — the scene lives in `./scene`.
//
// Unlike `Constellation`, this component renders its own container: the orb is
// bounded by the hero column rather than being a global fixed layer, so it must
// live inside the React tree and unmount with the screen.

import { useEffect, useRef } from "react";

import { useAppearance } from "@/store/appearance";
import { createLogoOrb, type LogoOrbHandle } from "./scene";

/** Served from the Vite public root. */
const LOGO_URL = "/assets/eme-3d-logo-cut.png";

export interface LogoOrbProps {
  className?: string;
}

/**
 * The landing hero's brandmark orb.
 *
 * Gated by the same `fx3d` setting as the constellation — Settings › Appearance
 * turning 3D effects off must take *every* WebGL scene down, not just the
 * background field. With it off the orb renders nothing and the hero degrades
 * to its left column.
 */
export function LogoOrb({ className }: LogoOrbProps) {
  const fx3d = useAppearance((s) => s.fx3d);
  const accent = useAppearance((s) => s.accent);
  const mode = useAppearance((s) => s.mode);
  const tilt = useAppearance((s) => s.tilt);

  const hostRef = useRef<HTMLDivElement | null>(null);
  const handleRef = useRef<LogoOrbHandle | null>(null);

  // Read inside the create effect without making these dependencies — all three
  // are applied live by the effects below, never by re-creating the scene.
  const accentRef = useRef(accent);
  const modeRef = useRef(mode);
  const tiltRef = useRef(tilt);
  accentRef.current = accent;
  modeRef.current = mode;
  tiltRef.current = tilt;

  useEffect(() => {
    const host = hostRef.current;
    if (!fx3d || !host) return;

    let handle: LogoOrbHandle | null = null;
    try {
      handle = createLogoOrb(host, {
        accent: accentRef.current,
        mode: modeRef.current,
        tilt: tiltRef.current,
        logoUrl: LOGO_URL,
      });
    } catch (err) {
      // No WebGL context (headless, blocklisted GPU, or the browser's per-page
      // context budget already spent on the constellation) — degrade to nothing.
      console.error("logo orb init failed", err);
    }
    handleRef.current = handle;

    return () => {
      handle?.dispose();
      handleRef.current = null;
    };
  }, [fx3d]);

  useEffect(() => {
    handleRef.current?.setAccent(accent);
  }, [accent]);

  useEffect(() => {
    handleRef.current?.setMode(mode);
  }, [mode]);

  useEffect(() => {
    handleRef.current?.setTilt(tilt);
  }, [tilt]);

  return <div ref={hostRef} aria-hidden="true" className={className} />;
}

export default LogoOrb;

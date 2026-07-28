// Handoff › Screens › "App shell" background stack, layer z-index:1, and
// Handoff › Interactions & Behavior › "3D constellation (background)".
//
// Owns nothing but lifecycle: the scene itself lives in `./scene`. Renders no
// DOM of its own — the canvas is appended to the shell's `#constellation-root`
// container (or, if the shell has not mounted one, to a fallback container this
// component creates and removes).

import { useEffect, useRef } from "react";

import { useAppearance } from "@/store/appearance";
import { createConstellation, type ConstellationHandle } from "./scene";

/** The stable container the app shell mounts in the fixed background stack. */
export const CONSTELLATION_ROOT_ID = "constellation-root";

const FALLBACK_ID = "constellation-root-fallback";

interface Container {
  el: HTMLElement;
  /** True when we created it and must remove it again. */
  owned: boolean;
}

/**
 * Use the shell's container when it exists; otherwise create an equivalent one.
 * The shell lands in a parallel PR, so both paths must work.
 */
function resolveContainer(): Container {
  const existing = document.getElementById(CONSTELLATION_ROOT_ID);
  if (existing) return { el: existing, owned: false };

  const reused = document.getElementById(FALLBACK_ID);
  if (reused) return { el: reused, owned: true };

  const el = document.createElement("div");
  el.id = FALLBACK_ID;
  el.style.position = "fixed";
  el.style.inset = "0";
  el.style.zIndex = "1";
  el.style.pointerEvents = "none";
  document.body.appendChild(el);
  return { el, owned: true };
}

/**
 * The ambient WebGL constellation field.
 *
 * No props: everything it needs (`fx3d`, `accent`, `mode`) comes from the
 * appearance store. Mount it once, anywhere in the tree.
 */
export function Constellation(): null {
  const fx3d = useAppearance((s) => s.fx3d);
  const accent = useAppearance((s) => s.accent);
  const mode = useAppearance((s) => s.mode);

  const handleRef = useRef<ConstellationHandle | null>(null);
  // Read inside the create effect without making it a dependency — accent and
  // mode are applied live by the two effects below, never by re-creating.
  const accentRef = useRef(accent);
  const modeRef = useRef(mode);
  accentRef.current = accent;
  modeRef.current = mode;

  // Create / tear down. `fx3d` is the only trigger.
  useEffect(() => {
    if (!fx3d) return;

    const container = resolveContainer();
    let handle: ConstellationHandle | null = null;
    try {
      handle = createConstellation(container.el, {
        accent: accentRef.current,
        mode: modeRef.current,
      });
    } catch (err) {
      // No WebGL context (headless, blocklisted GPU) — degrade to no field.
      console.error("constellation init failed", err);
    }
    handleRef.current = handle;

    return () => {
      handle?.dispose();
      handleRef.current = null;
      container.el.replaceChildren();
      if (container.owned) container.el.remove();
    };
  }, [fx3d]);

  // Live accent swap — no teardown.
  useEffect(() => {
    handleRef.current?.setAccent(accent);
  }, [accent]);

  // Live mode swap — blending + palette.
  useEffect(() => {
    handleRef.current?.setMode(mode);
  }, [mode]);

  return null;
}

export default Constellation;

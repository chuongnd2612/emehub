// ADR 0012 › "WebGL orb" — the landing hero's brandmark orb.
//
// Framework-free, exactly like `background/scene.ts`: this module owns the
// three.js scene and every GPU resource in it; the React layer owns only
// lifecycle. Live setters swap accent, mode and the Depth-on-hover setting
// without a teardown.
//
// Why WebGL and not a video: the reference design filters a purple `.webm`
// through `mix-blend-screen`, which cannot survive light mode — screen blending
// against a white page erases the asset. A scene we render ourselves reads the
// accent and the mode and stays correct in both. (ADR 0012 › Alternatives
// rejected.)

import {
  AdditiveBlending,
  BackSide,
  BufferGeometry,
  Clock,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  FrontSide,
  Group,
  IcosahedronGeometry,
  Mesh,
  MeshBasicMaterial,
  NormalBlending,
  PerspectiveCamera,
  PlaneGeometry,
  Points,
  PointsMaterial,
  Scene,
  ShaderMaterial,
  SRGBColorSpace,
  Texture,
  TextureLoader,
  WebGLRenderer,
} from "three";

import type { Accent, Mode } from "@/store/appearance";
import { ACCENT_HEX, ORB, orbPalette } from "./palette";

export interface LogoOrbHandle {
  setAccent: (accent: Accent) => void;
  setMode: (mode: Mode) => void;
  /** Depth-on-hover. When off the orb still spins, but ignores the pointer. */
  setTilt: (tilt: boolean) => void;
  dispose: () => void;
}

export interface LogoOrbOptions {
  accent: Accent;
  mode: Mode;
  tilt: boolean;
  /** Freezes motion and thins the particle shell. Defaults to the media query. */
  reducedMotion?: boolean;
  /** Path to the brandmark PNG, served from the Vite public root. */
  logoUrl: string;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Fresnel rim: brightness rises as the surface normal turns away from the
 * viewer, so the sphere is invisible face-on and blazes at the silhouette.
 * That edge-only emission is what makes a solid mesh read as a glass shell.
 */
const RIM_VERT = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

const RIM_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uPower;
  uniform float uOpacity;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    float f = pow(1.0 - abs(dot(normalize(vNormal), normalize(vView))), uPower);
    gl_FragColor = vec4(uColor * f, f * uOpacity);
  }
`;

/** Soft radial core: bright at the centre, gone by the edge. */
const CORE_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    float d = abs(dot(normalize(vNormal), normalize(vView)));
    float f = pow(d, 2.2);
    gl_FragColor = vec4(uColor * f, f * uOpacity);
  }
`;

export function createLogoOrb(
  container: HTMLElement,
  options: LogoOrbOptions,
): LogoOrbHandle {
  const reduce = options.reducedMotion ?? prefersReducedMotion();
  let palette = orbPalette(options.mode);
  let lightMode = options.mode === "light";
  let tiltEnabled = options.tilt;

  const size = (): { w: number; h: number } => {
    const r = container.getBoundingClientRect();
    // A zero-sized container (display:none, first paint) would make the
    // projection matrix NaN — clamp to something renderable.
    return { w: Math.max(1, r.width), h: Math.max(1, r.height) };
  };

  const scene = new Scene();
  const { w, h } = size();
  const camera = new PerspectiveCamera(
    ORB.cameraFov,
    w / h,
    ORB.cameraNear,
    ORB.cameraFar,
  );
  camera.position.z = ORB.cameraZ;

  const renderer = new WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  // `updateStyle: false` — the canvas is sized by CSS (100% of the host) and
  // the drawing buffer follows it. Letting three.js write a pixel width onto
  // the style instead feeds back into the host's `auto` grid track, which grows
  // the column, which resizes the canvas: a runaway that reached ~5000 px.
  renderer.setSize(w, h, false);
  const canvas = renderer.domElement;
  canvas.style.display = "block";
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.pointerEvents = "none";
  container.appendChild(canvas);

  const blending = (): typeof AdditiveBlending | typeof NormalBlending =>
    lightMode ? NormalBlending : AdditiveBlending;

  const group = new Group();
  scene.add(group);

  // ── Glass shell: two fresnel layers ──────────────────────────────────────
  // The back face is drawn with the neutral halo colour, so the far side of the
  // shell shows through the near side. That second, desaturated rim is what
  // gives the sphere volume rather than a flat ring.
  const shellGeom = new IcosahedronGeometry(ORB.radius, ORB.detail);

  const outerMat = new ShaderMaterial({
    uniforms: {
      uColor: { value: new Color(ACCENT_HEX[options.accent]) },
      uPower: { value: ORB.rimPowerOuter },
      uOpacity: { value: palette.rimOpacity },
    },
    vertexShader: RIM_VERT,
    fragmentShader: RIM_FRAG,
    transparent: true,
    blending: blending(),
    depthWrite: false,
    side: FrontSide,
  });

  const innerMat = new ShaderMaterial({
    uniforms: {
      uColor: { value: new Color(palette.halo) },
      uPower: { value: ORB.rimPowerInner },
      uOpacity: { value: palette.rimOpacity * palette.haloScale },
    },
    vertexShader: RIM_VERT,
    fragmentShader: RIM_FRAG,
    transparent: true,
    blending: blending(),
    depthWrite: false,
    side: BackSide,
  });

  const shellBack = new Mesh(shellGeom, innerMat);
  const shellFront = new Mesh(shellGeom, outerMat);
  group.add(shellBack, shellFront);

  // ── Inner core glow, in the accent ───────────────────────────────────────
  const coreGeom = new IcosahedronGeometry(ORB.radius * ORB.coreScale, 3);
  const coreMat = new ShaderMaterial({
    uniforms: {
      uColor: { value: new Color(ACCENT_HEX[options.accent]) },
      uOpacity: { value: palette.coreOpacity },
    },
    vertexShader: RIM_VERT,
    fragmentShader: CORE_FRAG,
    transparent: true,
    blending: blending(),
    depthWrite: false,
    side: BackSide,
  });
  const core = new Mesh(coreGeom, coreMat);
  group.add(core);

  // ── The brandmark, suspended in the front hemisphere ─────────────────────
  const logoGeom = new PlaneGeometry(
    ORB.logoWidth,
    ORB.logoWidth / ORB.logoAspect,
  );
  const logoMat = new MeshBasicMaterial({
    transparent: true,
    opacity: palette.logoOpacity,
    depthWrite: false,
    side: DoubleSide,
  });
  const logo = new Mesh(logoGeom, logoMat);
  logo.position.z = ORB.logoZ;
  // Its own group, NOT the spinning one: parented to `group` the plane orbits
  // the Y axis and drifts off the sphere's centre, and counter-rotating the
  // mesh fixes its facing but not its position. The shell spins around a mark
  // that stays put.
  const markGroup = new Group();
  markGroup.add(logo);
  scene.add(markGroup);

  let logoTex: Texture | null = null;
  const loader = new TextureLoader();
  loader.load(
    options.logoUrl,
    (tex) => {
      if (disposed) {
        tex.dispose();
        return;
      }
      tex.colorSpace = SRGBColorSpace;
      logoTex = tex;
      logoMat.map = tex;
      logoMat.needsUpdate = true;
    },
    undefined,
    // A missing texture must not take the orb down — the shell still renders.
    (err) => console.error("orb logo texture failed", err),
  );

  // ── Orbiting dust shell ──────────────────────────────────────────────────
  const dustCount = reduce ? ORB.dustCountReduced : ORB.dustCount;
  const dustPos = new Float32Array(dustCount * 3);
  for (let i = 0; i < dustCount; i++) {
    // Uniform direction on the unit sphere, then a random radius in the shell.
    const u = Math.random() * 2 - 1;
    const theta = Math.random() * Math.PI * 2;
    const s = Math.sqrt(1 - u * u);
    const r = ORB.dustInner + Math.random() * (ORB.dustOuter - ORB.dustInner);
    dustPos[i * 3] = r * s * Math.cos(theta);
    dustPos[i * 3 + 1] = r * s * Math.sin(theta);
    dustPos[i * 3 + 2] = r * u;
  }
  const dustGeom = new BufferGeometry();
  dustGeom.setAttribute("position", new Float32BufferAttribute(dustPos, 3));
  const dustMat = new PointsMaterial({
    size: ORB.dustSize,
    color: new Color(palette.dust),
    transparent: true,
    opacity: palette.dustOpacity,
    blending: blending(),
    depthWrite: false,
    sizeAttenuation: true,
  });
  const dust = new Points(dustGeom, dustMat);
  const dustGroup = new Group();
  dustGroup.add(dust);
  scene.add(dustGroup);

  // ── Live setters ─────────────────────────────────────────────────────────
  const setAccent = (accent: Accent): void => {
    (outerMat.uniforms.uColor.value as Color).setHex(ACCENT_HEX[accent]);
    (coreMat.uniforms.uColor.value as Color).setHex(ACCENT_HEX[accent]);
  };

  const setMode = (mode: Mode): void => {
    lightMode = mode === "light";
    palette = orbPalette(mode);
    const b = blending();
    outerMat.blending = b;
    innerMat.blending = b;
    coreMat.blending = b;
    dustMat.blending = b;
    outerMat.uniforms.uOpacity.value = palette.rimOpacity;
    innerMat.uniforms.uOpacity.value = palette.rimOpacity * palette.haloScale;
    (innerMat.uniforms.uColor.value as Color).setHex(palette.halo);
    coreMat.uniforms.uOpacity.value = palette.coreOpacity;
    dustMat.color.setHex(palette.dust);
    dustMat.opacity = palette.dustOpacity;
    logoMat.opacity = palette.logoOpacity;
    outerMat.needsUpdate = true;
    innerMat.needsUpdate = true;
    coreMat.needsUpdate = true;
    dustMat.needsUpdate = true;
  };

  const setTilt = (next: boolean): void => {
    tiltEnabled = next;
    if (!next) {
      tx = 0;
      ty = 0;
    }
  };

  // ── Pointer + resize ─────────────────────────────────────────────────────
  // The pointer is tracked window-wide rather than on the canvas: the orb has
  // `pointer-events:none`, and the parallax should respond to the cursor
  // anywhere in the hero, not only when it is over the sphere.
  let tx = 0;
  let ty = 0;
  const onMove = (e: MouseEvent): void => {
    if (!tiltEnabled) return;
    tx = e.clientX / window.innerWidth - 0.5;
    ty = e.clientY / window.innerHeight - 0.5;
  };
  window.addEventListener("mousemove", onMove);

  const onResize = (): void => {
    const { w: cw, h: ch } = size();
    camera.aspect = cw / ch;
    camera.updateProjectionMatrix();
    renderer.setSize(cw, ch, false);
  };
  // The hero column resizes with the layout, not only with the window (the
  // 2-up grid collapses to one column), so observe the container itself.
  const observer =
    typeof ResizeObserver === "function" ? new ResizeObserver(onResize) : null;
  observer?.observe(container);
  window.addEventListener("resize", onResize);

  // ── Loop ─────────────────────────────────────────────────────────────────
  const clock = new Clock();
  let raf = 0;
  let disposed = false;
  let rx = 0;
  let ry = 0;

  const animate = (): void => {
    raf = requestAnimationFrame(animate);
    if (document.hidden) return;

    const t = reduce ? 0 : clock.getElapsedTime();

    rx += (ty * ORB.tiltX - rx) * ORB.tiltEase;
    ry += (tx * ORB.tiltY - ry) * ORB.tiltEase;

    group.rotation.y = t * ORB.spinY + ry;
    group.rotation.x = rx;
    dustGroup.rotation.y = -t * ORB.dustSpin + ry * 0.6;
    dustGroup.rotation.x = rx * 0.6;

    const breathe = 1 + ORB.breatheAmp * Math.sin(t * ORB.breatheSpeed);
    shellFront.scale.setScalar(breathe);
    shellBack.scale.setScalar(breathe);

    // The brandmark only takes the parallax, never the spin — it tilts with the
    // pointer for depth and otherwise faces the reader square on.
    markGroup.rotation.y = ry * 0.5;
    markGroup.rotation.x = rx * 0.5;

    renderer.render(scene, camera);
  };
  animate();

  const dispose = (): void => {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(raf);
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("resize", onResize);
    observer?.disconnect();
    scene.remove(group, dustGroup, markGroup);
    group.clear();
    dustGroup.clear();
    markGroup.clear();
    shellGeom.dispose();
    coreGeom.dispose();
    logoGeom.dispose();
    dustGeom.dispose();
    outerMat.dispose();
    innerMat.dispose();
    coreMat.dispose();
    logoMat.dispose();
    dustMat.dispose();
    logoTex?.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    canvas.remove();
  };

  return { setAccent, setMode, setTilt, dispose };
}

"use client";

import React, { useEffect, useRef } from "react";

// Shared geometric "motive" — a deep-indigo low-poly mesh + glow accents, used
// across the landing, auth, and inner app pages at three intensities so every
// surface reads as the same product. Single source of truth (was previously
// inlined in LandingPage).
//   base bg     oklch(0.15 0.045 273)   — deep indigo navy
//   accent      oklch(0.58 0.17 250)    — clean tech blue
//   purple      oklch(0.50 0.17 295)    — secondary ambient wash

type Variant = "landing" | "auth" | "app";

// Per-variant appearance. Differentiation is by intensity + glow weight, not
// by introducing new hues.
const CFG: Record<
  Variant,
  {
    baseFill: string;
    groupOpacity: number;
    strokeOpacity: number;
    lineScale: number;
    purpleOpacity: number;
    blueOpacity: number;
  }
> = {
  // Toned down from the original hero mesh, but now spans the whole page.
  landing: {
    baseFill: "oklch(0.135 0.042 274)",
    groupOpacity: 1,
    strokeOpacity: 0.45,
    lineScale: 0.7,
    purpleOpacity: 0.34,
    blueOpacity: 0.15,
  },
  // Medium, blue-leaning — confined to the auth brand panel.
  auth: {
    baseFill: "oklch(0.135 0.038 273)",
    groupOpacity: 1,
    strokeOpacity: 0.42,
    lineScale: 0.55,
    purpleOpacity: 0.18,
    blueOpacity: 0.24,
  },
  // Faint overlay on the inner pages — triangles barely register so the data
  // stays the hero. Transparent base so the page --bg shows through.
  app: {
    baseFill: "transparent",
    groupOpacity: 0.5,
    strokeOpacity: 0.12,
    lineScale: 0.3,
    purpleOpacity: 0.12,
    blueOpacity: 0.1,
  },
};

// Low-poly mesh — indigo hue 273, refined navy tones (brighter top-right where
// the purple wash sits).
const TRIS = [
  // Top strip
  { pts: "0,0 180,0 90,95", l: 0.150 },
  { pts: "180,0 420,0 300,95", l: 0.158 },
  { pts: "420,0 660,0 540,95", l: 0.148 },
  { pts: "660,0 900,0 780,95", l: 0.168 },
  { pts: "900,0 1140,0 1020,95", l: 0.176 },
  { pts: "1140,0 1380,0 1260,95", l: 0.188 },
  { pts: "1380,0 1440,0 1440,95", l: 0.180 },
  { pts: "0,0 90,95 0,95", l: 0.168 },
  { pts: "180,0 300,95 90,95", l: 0.158 },
  { pts: "420,0 540,95 300,95", l: 0.150 },
  { pts: "660,0 780,95 540,95", l: 0.172 },
  { pts: "900,0 1020,95 780,95", l: 0.182 },
  { pts: "1140,0 1260,95 1020,95", l: 0.192 },
  { pts: "1380,0 1440,95 1260,95", l: 0.200 },
  // Second strip
  { pts: "0,95 90,95 0,195", l: 0.158 },
  { pts: "90,95 300,95 200,195", l: 0.148 },
  { pts: "300,95 540,95 440,195", l: 0.162 },
  { pts: "540,95 780,95 680,195", l: 0.158 },
  { pts: "780,95 1020,95 920,195", l: 0.172 },
  { pts: "1020,95 1260,95 1160,195", l: 0.182 },
  { pts: "1260,95 1440,95 1440,195", l: 0.190 },
  { pts: "0,195 200,195 90,95", l: 0.166 },
  { pts: "200,195 440,195 300,95", l: 0.152 },
  { pts: "440,195 680,195 540,95", l: 0.148 },
  { pts: "680,195 920,195 780,95", l: 0.166 },
  { pts: "920,195 1160,195 1020,95", l: 0.176 },
  { pts: "1160,195 1440,195 1260,95", l: 0.186 },
  // Third strip
  { pts: "0,195 200,195 110,295", l: 0.150 },
  { pts: "200,195 440,195 350,295", l: 0.160 },
  { pts: "440,195 680,195 590,295", l: 0.148 },
  { pts: "680,195 920,195 830,295", l: 0.164 },
  { pts: "920,195 1160,195 1070,295", l: 0.170 },
  { pts: "1160,195 1440,195 1440,295", l: 0.178 },
  { pts: "0,295 110,295 200,195", l: 0.162 },
  { pts: "110,295 350,295 200,195", l: 0.152 },
  { pts: "350,295 590,295 440,195", l: 0.146 },
  { pts: "590,295 830,295 680,195", l: 0.158 },
  { pts: "830,295 1070,295 920,195", l: 0.166 },
  { pts: "1070,295 1440,295 1160,195", l: 0.172 },
  // Fourth strip
  { pts: "0,295 110,295 0,395", l: 0.154 },
  { pts: "110,295 350,295 220,395", l: 0.146 },
  { pts: "350,295 590,295 460,395", l: 0.158 },
  { pts: "590,295 830,295 700,395", l: 0.148 },
  { pts: "830,295 1070,295 940,395", l: 0.158 },
  { pts: "1070,295 1440,295 1440,395", l: 0.164 },
  { pts: "0,395 220,395 110,295", l: 0.160 },
  { pts: "220,395 460,395 350,295", l: 0.150 },
  { pts: "460,395 700,395 590,295", l: 0.144 },
  { pts: "700,395 940,395 830,295", l: 0.154 },
  { pts: "940,395 1440,395 1070,295", l: 0.160 },
  // Fifth strip
  { pts: "0,395 220,395 130,495", l: 0.148 },
  { pts: "220,395 460,395 370,495", l: 0.142 },
  { pts: "460,395 700,395 610,495", l: 0.152 },
  { pts: "700,395 940,395 850,495", l: 0.148 },
  { pts: "940,395 1440,395 1440,495", l: 0.156 },
  { pts: "0,495 130,495 220,395", l: 0.154 },
  { pts: "130,495 370,495 220,395", l: 0.146 },
  { pts: "370,495 610,495 460,395", l: 0.140 },
  { pts: "610,495 850,495 700,395", l: 0.150 },
  { pts: "850,495 1440,495 940,395", l: 0.154 },
  // Sixth strip
  { pts: "0,495 130,495 0,595", l: 0.150 },
  { pts: "130,495 370,495 240,595", l: 0.142 },
  { pts: "370,495 610,495 480,595", l: 0.148 },
  { pts: "610,495 850,495 720,595", l: 0.142 },
  { pts: "850,495 1440,495 1440,595", l: 0.150 },
  { pts: "0,595 240,595 130,495", l: 0.156 },
  { pts: "240,595 480,595 370,495", l: 0.146 },
  { pts: "480,595 720,595 610,495", l: 0.140 },
  { pts: "720,595 1440,595 850,495", l: 0.148 },
  // Bottom
  { pts: "0,595 0,760 240,595", l: 0.148 },
  { pts: "0,760 480,760 240,595", l: 0.142 },
  { pts: "480,760 720,760 480,595", l: 0.146 },
  { pts: "480,760 720,595 720,760", l: 0.140 },
  { pts: "720,760 1440,760 720,595", l: 0.146 },
  { pts: "720,760 1440,595 1440,760", l: 0.144 },
];

// Soft accent edges — blue near the lower-left, a couple of purple ones top-right.
const GLOW_LINES = [
  { x1: 90,   y1: 95,  x2: 200, y2: 195, o: 0.48, c: "0.71 0.15 242" },
  { x1: 0,    y1: 195, x2: 110, y2: 295, o: 0.40, c: "0.71 0.15 242" },
  { x1: 350,  y1: 295, x2: 220, y2: 395, o: 0.38, c: "0.71 0.15 242" },
  { x1: 700,  y1: 395, x2: 610, y2: 495, o: 0.33, c: "0.71 0.15 242" },
  { x1: 1380, y1: 95,  x2: 1260, y2: 195, o: 0.43, c: "0.60 0.17 295" },
  { x1: 1160, y1: 195, x2: 1070, y2: 295, o: 0.35, c: "0.60 0.17 295" },
  { x1: 1020, y1: 95,  x2: 920, y2: 195, o: 0.30, c: "0.62 0.16 280" },
];

function PolyMesh({ variant }: { variant: Variant }) {
  const cfg = CFG[variant];
  const pid = `lp-purple-${variant}`;
  const bid = `lp-blue-${variant}`;
  const fid = `lp-soft-${variant}`;
  return (
    <svg
      aria-hidden
      className="absolute inset-0 w-full h-full"
      viewBox="0 0 1440 760"
      preserveAspectRatio="xMidYMid slice"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        {/* Purple-indigo wash in the upper-right */}
        <radialGradient id={pid} cx="82%" cy="14%" r="62%">
          <stop offset="0%" stopColor="oklch(0.50 0.19 295)" stopOpacity={cfg.purpleOpacity} />
          <stop offset="45%" stopColor="oklch(0.38 0.15 288)" stopOpacity={cfg.purpleOpacity * 0.34} />
          <stop offset="100%" stopColor="oklch(0.15 0.045 273)" stopOpacity="0" />
        </radialGradient>
        {/* Soft blue ambient lower-left to balance the composition */}
        <radialGradient id={bid} cx="12%" cy="58%" r="50%">
          <stop offset="0%" stopColor="oklch(0.52 0.16 250)" stopOpacity={cfg.blueOpacity} />
          <stop offset="100%" stopColor="transparent" stopOpacity="0" />
        </radialGradient>
        {/* Gentle single-pass glow — refined, not neon */}
        <filter id={fid} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {cfg.baseFill !== "transparent" && (
        <rect width="1440" height="760" fill={cfg.baseFill} />
      )}

      {/* Triangle mesh faces — indigo navy */}
      <g opacity={cfg.groupOpacity}>
        {TRIS.map((t, i) => (
          <polygon
            key={i}
            points={t.pts}
            fill={`oklch(${t.l} 0.045 273)`}
            stroke="oklch(0.27 0.055 272)"
            strokeWidth="0.7"
            strokeOpacity={cfg.strokeOpacity}
          />
        ))}
      </g>

      {/* Glow overlays */}
      <rect width="1440" height="760" fill={`url(#${pid})`} />
      <rect width="1440" height="760" fill={`url(#${bid})`} />

      {/* Soft accent edges (per-line color) */}
      {GLOW_LINES.map((l, i) => (
        <line
          key={i}
          x1={l.x1}
          y1={l.y1}
          x2={l.x2}
          y2={l.y2}
          stroke={`oklch(${l.c})`}
          strokeWidth="1.4"
          strokeOpacity={l.o * cfg.lineScale}
          filter={`url(#${fid})`}
        />
      ))}
    </svg>
  );
}

// Landing-only: a soft glow that follows the cursor. Coordinates are written to
// CSS custom properties directly (no React state per frame), throttled with rAF,
// and disabled under prefers-reduced-motion.
function CursorGlow() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const onMove = (e: PointerEvent) => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        el.style.setProperty("--mx", `${e.clientX}px`);
        el.style.setProperty("--my", `${e.clientY}px`);
        el.style.opacity = "1";
      });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden
      className="fixed inset-0 pointer-events-none"
      style={{
        zIndex: 0,
        opacity: 0,
        transition: "opacity 600ms ease-out",
        background:
          "radial-gradient(620px circle at var(--mx, 50%) var(--my, 50%), oklch(0.62 0.17 250 / 0.10), transparent 70%)",
      }}
    />
  );
}

export function MeshBackground({ variant }: { variant: Variant }) {
  const positioning =
    variant === "auth" ? "absolute inset-0 overflow-hidden" : "fixed inset-0";
  return (
    <>
      <div
        className={`${positioning} pointer-events-none`}
        aria-hidden
        style={{ zIndex: 0 }}
      >
        <PolyMesh variant={variant} />
      </div>
      {variant === "landing" && <CursorGlow />}
    </>
  );
}

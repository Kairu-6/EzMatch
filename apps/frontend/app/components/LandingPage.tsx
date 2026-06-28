"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Landmark, ArrowRight, FileText, Banknote, Receipt, Zap } from "lucide-react";

// Always-dark surface — OKLCH values hardcoded (not token-driven).
// Theme: deep indigo "tech" (Flex-IT inspired) — refined, not neon.
//   base bg       oklch(0.15 0.045 273)   — deep indigo navy
//   surface       oklch(0.19 0.045 272)   — card fill
//   ink           oklch(0.96 0.006 262)
//   ink-muted     oklch(0.61 0.020 266)
//   ink-subtle    oklch(0.49 0.018 268)
//   accent        oklch(0.58 0.17 250)    — clean tech blue
//   accent-hover  oklch(0.52 0.18 248)
//   accent-text   oklch(0.71 0.15 242)    — bright sky-blue (headings/edges)
//   accent-dim    oklch(0.26 0.09 262)    — badge bg
//   purple        oklch(0.50 0.17 295)    — secondary ambient (hero wash)
//   border        oklch(0.30 0.055 272)

const STEPS = [
  {
    num: 1,
    label: "Import invoices",
    desc: "Upload PDF, image, or CSV invoices in any currency",
    Icon: FileText,
  },
  {
    num: 2,
    label: "Connect bank feeds",
    desc: "Link your bank statements — MYR, USD, SGD and more",
    Icon: Banknote,
  },
  {
    num: 3,
    label: "Upload payment proofs",
    desc: "Attach wire receipts and confirmation documents",
    Icon: Receipt,
  },
  {
    num: 4,
    label: "Run reconciliation",
    desc: "AI matches transactions to invoices across currencies",
    Icon: Zap,
  },
];

// Low-poly mesh — indigo hue 273, refined navy tones (brighter top-right
// where the purple hero wash sits, like the reference's diagonal split).
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

// Soft accent edges — blue near the hero, a couple purple ones top-right
// to echo the reference's blue→purple split. Subtle, not neon.
const GLOW_LINES = [
  { x1: 90,   y1: 95,  x2: 200, y2: 195, o: 0.48, c: "0.71 0.15 242" },
  { x1: 0,    y1: 195, x2: 110, y2: 295, o: 0.40, c: "0.71 0.15 242" },
  { x1: 350,  y1: 295, x2: 220, y2: 395, o: 0.38, c: "0.71 0.15 242" },
  { x1: 700,  y1: 395, x2: 610, y2: 495, o: 0.33, c: "0.71 0.15 242" },
  { x1: 1380, y1: 95,  x2: 1260, y2: 195, o: 0.43, c: "0.60 0.17 295" },
  { x1: 1160, y1: 195, x2: 1070, y2: 295, o: 0.35, c: "0.60 0.17 295" },
  { x1: 1020, y1: 95,  x2: 920, y2: 195, o: 0.30, c: "0.62 0.16 280" },
];

function PolyMesh() {
  return (
    <svg
      aria-hidden
      className="absolute inset-0 w-full h-full"
      viewBox="0 0 1440 760"
      preserveAspectRatio="xMidYMid slice"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        {/* Purple-indigo wash in the upper-right — the reference's hero glow */}
        <radialGradient id="lp-purple" cx="82%" cy="14%" r="62%">
          <stop offset="0%"   stopColor="oklch(0.50 0.19 295)" stopOpacity="0.38" />
          <stop offset="45%"  stopColor="oklch(0.38 0.15 288)" stopOpacity="0.13" />
          <stop offset="100%" stopColor="oklch(0.15 0.045 273)" stopOpacity="0" />
        </radialGradient>
        {/* Soft blue ambient lower-left to balance the composition */}
        <radialGradient id="lp-blue" cx="12%" cy="58%" r="50%">
          <stop offset="0%"   stopColor="oklch(0.52 0.16 250)" stopOpacity="0.15" />
          <stop offset="100%" stopColor="transparent" stopOpacity="0" />
        </radialGradient>
        {/* Gentle single-pass glow — refined, not neon */}
        <filter id="lp-soft" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Darkest base — deep indigo */}
      <rect width="1440" height="760" fill="oklch(0.135 0.042 274)" />

      {/* Triangle mesh faces — indigo navy */}
      {TRIS.map((t, i) => (
        <polygon
          key={i}
          points={t.pts}
          fill={`oklch(${t.l} 0.045 273)`}
          stroke="oklch(0.27 0.055 272)"
          strokeWidth="0.7"
          strokeOpacity="0.69"
        />
      ))}

      {/* Glow overlays */}
      <rect width="1440" height="760" fill="url(#lp-purple)" />
      <rect width="1440" height="760" fill="url(#lp-blue)" />

      {/* Soft accent edges (per-line color) */}
      {GLOW_LINES.map((l, i) => (
        <line
          key={i}
          x1={l.x1} y1={l.y1}
          x2={l.x2} y2={l.y2}
          stroke={`oklch(${l.c})`}
          strokeWidth="1.4"
          strokeOpacity={l.o}
          filter="url(#lp-soft)"
        />
      ))}
    </svg>
  );
}

export function LandingPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      className="relative min-h-screen overflow-x-hidden"
      style={{ background: "oklch(0.15 0.045 273)", color: "oklch(0.96 0.006 262)" }}
    >
      <style>{`
        .lp-nav-link {
          color: oklch(0.61 0.020 266);
          transition: color 150ms ease-out;
        }
        .lp-nav-link:hover { color: oklch(0.90 0.008 260); }

        .lp-btn-primary {
          background: oklch(0.54 0.16 264 / 0.90);
          color: oklch(0.99 0 0);
          border: 1px solid oklch(0.74 0.13 258 / 0.35);
          transition: background 150ms ease-out, box-shadow 150ms ease-out,
                      border-color 150ms ease-out;
        }
        .lp-btn-primary:hover {
          background: oklch(0.49 0.18 264 / 0.97);
          border-color: oklch(0.78 0.13 256 / 0.50);
          box-shadow: 0 0 18px oklch(0.55 0.17 264 / 0.28);
        }

        .lp-step {
          background: oklch(0.19 0.045 272 / 0.70);
          border: 1px solid oklch(0.30 0.055 272 / 0.65);
          transition: background 150ms ease-out, border-color 150ms ease-out,
                      transform 150ms ease-out, box-shadow 150ms ease-out;
          cursor: default;
        }
        .lp-step:hover {
          background: oklch(0.22 0.050 272 / 0.85);
          border-color: oklch(0.50 0.14 252 / 0.55);
          transform: translateY(-1px);
          box-shadow: 0 0 14px oklch(0.55 0.16 250 / 0.10);
        }

        @media (prefers-reduced-motion: reduce) {
          .lp-reveal, .lp-reveal-item {
            transition: opacity 0.25s ease-out !important;
          }
          .lp-step:hover { transform: none; box-shadow: none; }
          .lp-btn-primary:hover { box-shadow: none; }
        }
      `}</style>

      {/* Polygon mesh background */}
      <div
        className="absolute inset-0 overflow-hidden pointer-events-none"
        aria-hidden
        style={{ zIndex: 0 }}
      >
        <PolyMesh />
      </div>

      {/* ── Navbar ─────────────────────────────────────────────── */}
      <header
        className="fixed top-0 left-0 right-0 flex items-center justify-between px-5 sm:px-8 h-16"
        style={{
          zIndex: 20,
          background: "oklch(0.145 0.045 273 / 0.88)",
          backdropFilter: "blur(14px)",
          WebkitBackdropFilter: "blur(14px)",
          borderBottom: "1px solid oklch(0.30 0.055 272 / 0.60)",
        }}
      >
        {/* Logotype */}
        <div className="flex items-center gap-2.5">
          <span
            className="flex items-center justify-center w-8 h-8 rounded-md shrink-0"
            style={{
              background: "oklch(1 0 0 / 0.10)",
              border: "1px solid oklch(1 0 0 / 0.22)",
              backdropFilter: "blur(4px)",
              WebkitBackdropFilter: "blur(4px)",
            }}
            aria-hidden
          >
            <Landmark className="w-[18px] h-[18px]" style={{ color: "oklch(0.97 0 0)" }} />
          </span>
          <span
            className="font-semibold text-sm tracking-tight"
            style={{ color: "oklch(0.96 0.006 262)" }}
          >
            TreasuryFlow{" "}
            <span style={{ color: "oklch(0.49 0.018 268)", fontWeight: 400 }}>AI</span>
          </span>
        </div>

        {/* Nav */}
        <nav className="flex items-center gap-1" aria-label="Site navigation">
          <Link
            href="/login"
            className="lp-nav-link px-4 h-9 inline-flex items-center text-sm font-medium rounded-md outline-none focus-visible:ring-2 focus-visible:ring-[oklch(0.58_0.17_250)]"
          >
            Log in
          </Link>
          <Link
            href="/signup"
            className="lp-btn-primary px-4 h-9 inline-flex items-center text-sm font-medium rounded-md outline-none focus-visible:ring-2 focus-visible:ring-[oklch(0.71_0.15_242)]"
          >
            Sign up
          </Link>
        </nav>
      </header>

      {/* ── Hero ───────────────────────────────────────────────── */}
      <main className="relative" style={{ zIndex: 1 }}>
        <section
          className="min-h-screen flex items-center pt-16"
          aria-labelledby="lp-headline"
        >
          <div className="max-w-7xl mx-auto w-full px-5 sm:px-8 lg:px-12 py-20 lg:py-28">
            <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-14 lg:gap-20 items-center">

              {/* Left: headline + CTA */}
              <div>
                <h1
                  id="lp-headline"
                  className="lp-reveal font-semibold leading-[1.1]"
                  style={{
                    fontSize: "clamp(2.4rem, 5.2vw, 4.5rem)",
                    color: "oklch(0.97 0.007 252)",
                    textWrap: "balance",
                    letterSpacing: "-0.025em",
                    opacity: mounted ? 1 : 0,
                    transform: mounted ? "translateY(0)" : "translateY(22px)",
                    transition: "opacity 0.65s ease-out, transform 0.65s ease-out",
                    transitionDelay: "0ms",
                  }}
                >
                  Reconcile across borders,{" "}
                  <span
                    style={{
                      color: "oklch(0.71 0.15 242)",
                      textShadow: "0 0 24px oklch(0.58 0.17 250 / 0.28)",
                    }}
                  >
                    not spreadsheets.
                  </span>
                </h1>

                <p
                  className="lp-reveal mt-6 leading-relaxed"
                  style={{
                    fontSize: "1rem",
                    color: "oklch(0.61 0.020 266)",
                    maxWidth: "52ch",
                    opacity: mounted ? 1 : 0,
                    transform: mounted ? "translateY(0)" : "translateY(18px)",
                    transition: "opacity 0.65s ease-out, transform 0.65s ease-out",
                    transitionDelay: "90ms",
                  }}
                >
                  Stop manually tracking currency conversions and hidden banking
                  fees. TreasuryFlow AI matches your multi-currency bank feeds to
                  open invoices instantly — with a full, auditable trail.
                </p>

                <div
                  className="lp-reveal mt-10"
                  style={{
                    opacity: mounted ? 1 : 0,
                    transform: mounted ? "translateY(0)" : "translateY(14px)",
                    transition: "opacity 0.65s ease-out, transform 0.65s ease-out",
                    transitionDelay: "175ms",
                  }}
                >
                  <Link
                    href="/signup"
                    className="lp-btn-primary inline-flex items-center gap-2 px-6 h-11 rounded-md text-sm font-medium outline-none focus-visible:ring-2"
                  >
                    Get started
                    <ArrowRight className="w-4 h-4" aria-hidden />
                  </Link>
                </div>
              </div>

              {/* Right: how it works */}
              <div id="how-it-works">
                {/* Quiet anchor label — balances the left column's hierarchy.
                    Sentence case, not an uppercase tracked eyebrow. */}
                <p
                  className="lp-reveal-item text-sm font-medium mb-5"
                  style={{
                    color: "oklch(0.62 0.020 266)",
                    opacity: mounted ? 1 : 0,
                    transform: mounted ? "translateY(0)" : "translateY(12px)",
                    transition:
                      "opacity 0.55s ease-out 175ms, transform 0.55s ease-out 175ms",
                  }}
                >
                  How it works
                </p>

                <div
                  role="list"
                  aria-label="How TreasuryFlow AI works"
                  className="flex flex-col gap-4"
                >
                  {STEPS.map(({ num, label, desc, Icon }, i) => (
                    <div
                      key={num}
                      role="listitem"
                      className="lp-reveal-item lp-step flex items-start gap-4 p-4 sm:p-5 rounded-xl"
                      style={{
                        marginLeft: `${i * 16}px`,
                        opacity: mounted ? 1 : 0,
                        transform: mounted ? "translateY(0)" : "translateY(14px)",
                        transition: `opacity 0.55s ease-out ${260 + i * 90}ms, transform 0.55s ease-out ${260 + i * 90}ms`,
                      }}
                    >
                    {/* Step badge */}
                    <span
                      className="flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold shrink-0 mt-0.5"
                      style={{
                        background: "oklch(0.26 0.09 262)",
                        color: "oklch(0.78 0.14 244)",
                      }}
                      aria-label={`Step ${num}`}
                    >
                      {num}
                    </span>

                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <Icon
                          className="w-3.5 h-3.5 shrink-0"
                          style={{ color: "oklch(0.71 0.15 242)" }}
                          aria-hidden
                        />
                        <p
                          className="text-sm font-medium"
                          style={{ color: "oklch(0.89 0.008 260)" }}
                        >
                          {label}
                        </p>
                      </div>
                      <p
                        className="text-xs leading-relaxed"
                        style={{ color: "oklch(0.49 0.018 268)" }}
                      >
                        {desc}
                      </p>
                    </div>
                  </div>
                  ))}
                </div>
              </div>

            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

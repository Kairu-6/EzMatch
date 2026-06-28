"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Landmark, ArrowRight, FileText, Banknote, Receipt, Zap,
  AlertTriangle, Hourglass, ArrowRightLeft, XCircle, CheckCircle2,
} from "lucide-react";
import { MeshBackground } from "./MeshBackground";

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

// Agitate — industry-standard pain points of manual reconciliation.
const PAIN_POINTS = [
  {
    Icon: AlertTriangle,
    title: "3-5% revenue leakage",
    body: "Human error in manual spreadsheet matching leads to unrecorded variances and lost capital.",
  },
  {
    Icon: Hourglass,
    title: "15+ hours wasted weekly",
    body: "Finance teams spend days matching line items instead of analyzing strategic growth.",
  },
  {
    Icon: ArrowRightLeft,
    title: "Untracked FX spreads",
    body: "Hidden banking fees and fluctuating exchange rates create discrepancies in expected revenue.",
  },
];

// Solve — old-way vs new-way comparison rows (illustrative).
const OLD_WAY = ["Row 42: FX mismatch", "Unidentified wire fee", "14 hours remaining"];
const NEW_WAY = [
  "Matched RM 11,226 · Invoice #902",
  "Auto-resolved $15 intermediary fee",
  "Reconciliation complete in 0.4s",
];

// Scroll-reveal via IntersectionObserver (no scroll listener). Fires once.
// Reduced-motion users are treated as already-revealed, with no transition.
function useInView(threshold = 0.2) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);
  const [reduce, setReduce] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setReduce(true);
      setInView(true);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setInView(true);
            io.disconnect();
            break;
          }
        }
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);

  return { ref, inView, reduce };
}

// Reveal — fades + lifts its children once they scroll into view (staggered by `delay`).
function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const { ref, inView, reduce } = useInView();
  return (
    <div
      ref={ref}
      className={className}
      style={
        reduce
          ? undefined
          : {
              opacity: inView ? 1 : 0,
              transform: inView ? "translateY(0)" : "translateY(20px)",
              transition: `opacity 0.6s ease-out ${delay}ms, transform 0.6s ease-out ${delay}ms`,
            }
      }
    >
      {children}
    </div>
  );
}

// Functional ROI calculator. Assumptions are illustrative and shown to the user.
function RoiCalculator() {
  const [hours, setHours] = useState(15);
  const AUTOMATION = 0.9; // share of manual matching automated
  const RATE = 45; // RM/hr, fully-loaded finance cost
  const WEEKS = 48; // working weeks/year
  const hoursSavedYear = Math.round(hours * AUTOMATION * WEEKS);
  const costSaved = hoursSavedYear * RATE;
  const fmt = (n: number) => n.toLocaleString("en-MY");

  return (
    <div className="lp-panel rounded-xl p-6 sm:p-8 max-w-3xl mx-auto">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-10 items-center">
        {/* Control */}
        <div>
          <label
            htmlFor="lp-roi"
            className="block text-sm font-medium mb-1"
            style={{ color: "oklch(0.89 0.008 260)" }}
          >
            Hours spent on manual reconciliation each week
          </label>
          <p className="text-xs mb-5" style={{ color: "oklch(0.55 0.018 268)" }}>
            Drag to estimate what TreasuryFlow AI could give back.
          </p>
          <input
            id="lp-roi"
            type="range"
            min={2}
            max={40}
            step={1}
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="lp-range"
            aria-valuetext={`${hours} hours per week`}
          />
          <div className="mt-3 flex items-baseline gap-1.5">
            <span
              style={{
                fontFamily: "var(--font-jetbrains-mono), monospace",
                fontSize: "1.5rem",
                color: "oklch(0.71 0.15 242)",
              }}
            >
              {hours}
            </span>
            <span className="text-sm" style={{ color: "oklch(0.61 0.020 266)" }}>
              hours / week
            </span>
          </div>
        </div>

        {/* Output */}
        <div className="flex flex-col gap-5">
          <div>
            <p className="text-xs mb-1.5" style={{ color: "oklch(0.55 0.018 268)" }}>
              Estimated hours saved / year
            </p>
            <p
              style={{
                fontFamily: "var(--font-jetbrains-mono), monospace",
                fontSize: "2rem",
                lineHeight: 1,
                color: "oklch(0.85 0.10 150)",
              }}
            >
              {fmt(hoursSavedYear)}
            </p>
          </div>
          <div>
            <p className="text-xs mb-1.5" style={{ color: "oklch(0.55 0.018 268)" }}>
              Estimated cost recovered / year
            </p>
            <p
              style={{
                fontFamily: "var(--font-jetbrains-mono), monospace",
                fontSize: "2rem",
                lineHeight: 1,
                color: "oklch(0.85 0.10 150)",
              }}
            >
              RM {fmt(costSaved)}
            </p>
          </div>
        </div>
      </div>

      <div
        className="mt-7 pt-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
        style={{ borderTop: "1px solid oklch(0.30 0.055 272 / 0.65)" }}
      >
        <p
          className="text-xs leading-relaxed"
          style={{ color: "oklch(0.49 0.018 268)", maxWidth: "46ch" }}
        >
          Estimate only. Assumes about 90% of matching automated, at RM 45 per hour
          fully-loaded cost, across 48 working weeks.
        </p>
        <Link
          href="/signup"
          className="lp-btn-primary inline-flex items-center justify-center gap-2 px-6 h-11 rounded-md text-sm font-medium shrink-0 outline-none focus-visible:ring-2"
        >
          Get started
          <ArrowRight className="w-4 h-4" aria-hidden />
        </Link>
      </div>
    </div>
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

        /* Pain-point cards — same glass family as .lp-step */
        .lp-card {
          background: oklch(0.19 0.045 272 / 0.70);
          border: 1px solid oklch(0.30 0.055 272 / 0.65);
          transition: background 150ms ease-out, border-color 150ms ease-out,
                      transform 150ms ease-out, box-shadow 150ms ease-out;
        }
        .lp-card:hover {
          background: oklch(0.22 0.050 272 / 0.85);
          border-color: oklch(0.50 0.14 252 / 0.55);
          transform: translateY(-2px);
          box-shadow: 0 0 22px oklch(0.55 0.16 250 / 0.12);
        }

        /* Comparison + calculator panels */
        .lp-panel {
          background: oklch(0.185 0.044 272 / 0.55);
          border: 1px solid oklch(0.30 0.055 272 / 0.65);
        }

        /* Range slider — themed in the page accent blue */
        .lp-range {
          -webkit-appearance: none;
          appearance: none;
          width: 100%;
          height: 6px;
          border-radius: 999px;
          background: oklch(0.30 0.055 272 / 0.85);
          outline: none;
        }
        .lp-range::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: oklch(0.62 0.17 250);
          border: 2px solid oklch(0.85 0.10 245);
          cursor: pointer;
          box-shadow: 0 0 12px oklch(0.58 0.17 250 / 0.45);
          transition: transform 120ms ease-out;
        }
        .lp-range::-webkit-slider-thumb:hover { transform: scale(1.12); }
        .lp-range::-moz-range-thumb {
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: oklch(0.62 0.17 250);
          border: 2px solid oklch(0.85 0.10 245);
          cursor: pointer;
          box-shadow: 0 0 12px oklch(0.58 0.17 250 / 0.45);
        }
        .lp-range:focus-visible::-webkit-slider-thumb {
          outline: 2px solid oklch(0.71 0.15 242);
          outline-offset: 2px;
        }
        .lp-range:focus-visible::-moz-range-thumb {
          outline: 2px solid oklch(0.71 0.15 242);
          outline-offset: 2px;
        }

        @media (prefers-reduced-motion: reduce) {
          .lp-reveal, .lp-reveal-item {
            transition: opacity 0.25s ease-out !important;
          }
          .lp-step:hover { transform: none; box-shadow: none; }
          .lp-card:hover { transform: none; box-shadow: none; }
          .lp-btn-primary:hover { box-shadow: none; }
          .lp-range::-webkit-slider-thumb:hover { transform: none; }
        }
      `}</style>

      {/* Geometric motive — full-page fixed mesh + cursor glow. */}
      <MeshBackground variant="landing" />

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
        <Link
          href="/"
          aria-label="TreasuryFlow AI home"
          className="flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-[oklch(0.71_0.15_242)]"
        >
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
        </Link>

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

        {/* ── Agitate: the cost of manual reconciliation ────────── */}
        <section aria-labelledby="lp-pain-title" className="relative">
          <div className="max-w-7xl mx-auto w-full px-5 sm:px-8 lg:px-12 py-20 lg:py-28">
            <Reveal className="max-w-2xl mx-auto text-center">
              <h2
                id="lp-pain-title"
                className="font-semibold leading-[1.15]"
                style={{
                  fontSize: "clamp(1.9rem, 3.6vw, 3rem)",
                  color: "oklch(0.96 0.006 262)",
                  letterSpacing: "-0.02em",
                  textWrap: "balance",
                }}
              >
                The silent cost of manual reconciliation.
              </h2>
              <p
                className="mt-4 leading-relaxed mx-auto"
                style={{
                  fontSize: "1rem",
                  color: "oklch(0.61 0.020 266)",
                  maxWidth: "50ch",
                }}
              >
                Cross-border commerce is complex. Managing it in spreadsheets is
                quietly costing you margins.
              </p>
            </Reveal>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-12 lg:mt-16">
              {PAIN_POINTS.map(({ Icon, title, body }, i) => (
                <Reveal key={title} delay={i * 110} className="lp-card rounded-xl p-6 sm:p-7">
                  <span
                    className="flex items-center justify-center w-11 h-11 rounded-lg mb-5"
                    style={{
                      background: "oklch(0.26 0.09 262)",
                      border: "1px solid oklch(0.45 0.12 255 / 0.40)",
                    }}
                    aria-hidden
                  >
                    <Icon className="w-5 h-5" style={{ color: "oklch(0.71 0.15 242)" }} />
                  </span>
                  <h3
                    className="font-semibold text-lg mb-2"
                    style={{ color: "oklch(0.92 0.008 260)" }}
                  >
                    {title}
                  </h3>
                  <p
                    className="text-sm leading-relaxed"
                    style={{ color: "oklch(0.61 0.020 266)" }}
                  >
                    {body}
                  </p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* ── Solve: old way vs new way, plus ROI calculator ────── */}
        <section aria-labelledby="lp-solve-title" className="relative">
          <div className="max-w-7xl mx-auto w-full px-5 sm:px-8 lg:px-12 pb-20 lg:pb-28">
            <Reveal className="max-w-2xl mx-auto text-center">
              <h2
                id="lp-solve-title"
                className="font-semibold leading-[1.15]"
                style={{
                  fontSize: "clamp(1.9rem, 3.6vw, 3rem)",
                  color: "oklch(0.96 0.006 262)",
                  letterSpacing: "-0.02em",
                  textWrap: "balance",
                }}
              >
                Stop hunting for missing decimals.
              </h2>
              <p
                className="mt-4 leading-relaxed mx-auto"
                style={{
                  fontSize: "1rem",
                  color: "oklch(0.61 0.020 266)",
                  maxWidth: "52ch",
                }}
              >
                See how TreasuryFlow AI turns raw bank data into a clean, auditable
                match.
              </p>
            </Reveal>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-12 lg:mt-16">
              {/* Left: the old way */}
              <Reveal className="lp-panel rounded-xl overflow-hidden">
                <div
                  className="px-5 py-3"
                  style={{ borderBottom: "1px solid oklch(0.30 0.055 272 / 0.65)" }}
                >
                  <span
                    className="text-xs font-medium"
                    style={{ color: "oklch(0.61 0.020 266)" }}
                  >
                    The old way: spreadsheets
                  </span>
                </div>
                <div
                  className="p-4 sm:p-5 flex flex-col gap-2.5"
                  style={{ fontFamily: "var(--font-jetbrains-mono), monospace" }}
                >
                  {OLD_WAY.map((t) => (
                    <div
                      key={t}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-md"
                      style={{
                        background: "oklch(0.33 0.08 25 / 0.14)",
                        border: "1px solid oklch(0.50 0.15 25 / 0.30)",
                      }}
                    >
                      <XCircle
                        className="w-4 h-4 shrink-0"
                        style={{ color: "oklch(0.72 0.16 25)" }}
                        aria-hidden
                      />
                      <span
                        className="text-xs sm:text-sm"
                        style={{ color: "oklch(0.82 0.10 28)" }}
                      >
                        {t}
                      </span>
                    </div>
                  ))}
                </div>
              </Reveal>

              {/* Right: the new way */}
              <Reveal delay={120} className="lp-panel rounded-xl overflow-hidden">
                <div
                  className="px-5 py-3"
                  style={{ borderBottom: "1px solid oklch(0.30 0.055 272 / 0.65)" }}
                >
                  <span
                    className="text-xs font-medium"
                    style={{ color: "oklch(0.71 0.15 242)" }}
                  >
                    The new way: TreasuryFlow AI
                  </span>
                </div>
                <div className="p-4 sm:p-5 flex flex-col gap-2.5">
                  {NEW_WAY.map((t) => (
                    <div
                      key={t}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-md"
                      style={{
                        background: "oklch(0.30 0.06 150 / 0.16)",
                        border: "1px solid oklch(0.50 0.12 150 / 0.30)",
                      }}
                    >
                      <CheckCircle2
                        className="w-4 h-4 shrink-0"
                        style={{ color: "oklch(0.72 0.13 150)" }}
                        aria-hidden
                      />
                      <span
                        className="text-xs sm:text-sm"
                        style={{ color: "oklch(0.86 0.09 150)" }}
                      >
                        {t}
                      </span>
                    </div>
                  ))}
                </div>
              </Reveal>
            </div>

            <Reveal delay={80} className="mt-6">
              <RoiCalculator />
            </Reveal>
          </div>
        </section>
      </main>
    </div>
  );
}

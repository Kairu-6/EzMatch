# Design

Visual system for **ezMatch**. Register: product. Lane: institutional trust (Mercury / Stripe) — calm, precise, banking-grade. All color in OKLCH; tokens defined in `apps/frontend/app/globals.css` and consumed as semantic Tailwind v4 classes.

## Theme

Light and dark are both first-class, fully token-driven, and meet WCAG 2.1 AA equally. Dark is a deep cool slate (not pure black); light is a near-white cool neutral. Theme is class-based (`.dark` on `<html>`), defaults to system preference on first visit, persists the user's choice, and renders with no flash.

## Color

### Neutrals (cool slate)
| Role | Light | Dark | Use |
|---|---|---|---|
| `bg` | `oklch(0.985 0.002 240)` | `oklch(0.17 0.012 250)` | app background |
| `surface` | `oklch(1 0 0)` | `oklch(0.21 0.014 250)` | cards, panels, content |
| `surface-2` | `oklch(0.97 0.004 240)` | `oklch(0.145 0.012 250)` | sidebar, toolbars, table headers (second neutral layer) |
| `border` | `oklch(0.92 0.004 240)` | `oklch(0.28 0.014 250)` | hairline dividers, card edges |
| `border-strong` | `oklch(0.86 0.005 240)` | `oklch(0.36 0.014 250)` | inputs, emphasis borders |
| `ink` | `oklch(0.22 0.01 250)` | `oklch(0.96 0.004 250)` | primary text (~13:1) |
| `ink-muted` | `oklch(0.45 0.01 250)` | `oklch(0.72 0.008 250)` | secondary text (≥4.5:1) |
| `ink-subtle` | `oklch(0.55 0.01 250)` | `oklch(0.6 0.01 250)` | tertiary / large text only |

### Accent — deep teal
Primary actions, current selection, and focus rings **only**. Never decoration.
- `accent` light `oklch(0.55 0.10 195)`, dark `oklch(0.68 0.11 195)`
- `accent-hover` light `oklch(0.49 0.11 195)`, dark `oklch(0.74 0.10 195)`
- `accent-fg` `oklch(0.99 0 0)` (text/icon on accent fill)
- `accent-subtle` light `oklch(0.95 0.03 195)`, dark `oklch(0.30 0.05 195)` — selected rows, focus halos, quiet emphasis

### Semantic (distinct from accent)
Each has a base, a `-subtle` background, and a readable `-fg` for badges. Never conveyed by color alone — always paired with icon + text.
- `success` `oklch(0.62 0.14 150)` — matched, reconciled, cleared
- `warning` `oklch(0.75 0.13 75)` — pending, partial match, needs review
- `danger` `oklch(0.58 0.18 25)` — error, high risk, failed
- `info` `oklch(0.60 0.13 250)` — neutral/informational

Color strategy: **Restrained.** Tinted cool neutrals + one accent; semantic colors used only for state.

## Typography

- **UI sans:** Inter (`next/font`), weights 400 / 500 / 600. One family carries headings, labels, body, buttons. Headings are weight 600, sentence case — no `font-black`, no all-caps headings. Sparing uppercase micro-labels (e.g. table column heads) allowed; never an eyebrow on every section.
- **Mono:** JetBrains Mono — transaction IDs, reference hashes, and the activity log only. Monetary amounts use Inter with `font-variant-numeric: tabular-nums`.
- **Scale** (fixed rem, ratio ~1.2, 14px base): `xs .75rem / sm .8125rem / base .875rem / md 1rem / lg 1.125rem / xl 1.375rem / 2xl 1.75rem / 3xl 2.25rem`.
- `text-wrap: balance` on headings; prose capped 65–75ch.

## Shape, elevation, depth

- **Radius:** `sm 6px`, `md 8px` (default — buttons, inputs, cards), `lg 12px` (large panels), `full` (pills). One card radius across the app.
- **Shadow:** `sm` for resting cards, `md` for popovers/dialogs/drawer. Dark mode favors borders + a faint top highlight over heavy shadow.
- **Z-index scale:** dropdown 10 → sticky 20 → modal-backdrop 30 → modal 40 → toast 50 → tooltip 60. No arbitrary literals.

## Components

`apps/frontend/app/components/ui/`. Every interactive component ships **default / hover / focus-visible / active / disabled / loading**.

- **Button** — primary (accent fill), secondary (surface + border), ghost, danger; sizes sm/md; loading spinner; visible focus ring.
- **Field / Input** — label, hint, error; accent focus ring; standard control vocabulary.
- **Panel** — one card shape, optional header row; replaces the identical-card-grid reflex.
- **DataTable** — sticky `surface-2` header, row hover, tabular-nums cells, horizontal-scroll wrapper, empty + skeleton slots.
- **StatusPill** — semantic variants with lucide icon + text (replaces emoji badges).
- **Tabs / SegmentedControl**, **Skeleton** (replaces in-content spinners), **EmptyState** (teaches the interface), **Toast**, **Dropzone** (unified upload), **RingProgress** (SVG `stroke-dasharray`), **ActivityDrawer** (collapsible telemetry, honest copy), **PageHeader** (route title + primary action), **SidebarNav** (active = `surface-2` fill + accent text/icon + medium weight; **no side-stripe border**).

## Layout

- App shell: fixed sidebar on `surface-2`; content on `bg`; per-route `PageHeader`.
- Responsive is **structural**: sidebar collapses to icon rail / drawer below `md`; tables scroll horizontally. No fluid typography.

## Motion

- 150–250 ms, ease-out. Motion conveys state/feedback/reveal only — never decoration. No orchestrated page-load.
- Drawer slides; rows and skeletons cross-fade; staggered list reveals where a list genuinely enters.
- Every animation has a `@media (prefers-reduced-motion: reduce)` fallback (instant / crossfade). Plain CSS transitions; no motion library unless a specific effect demands it.

## Bans (enforced)

Side-stripe borders · gradient text · decorative glassmorphism · hero-metric template · identical card grids · uppercase tracked eyebrow on every section · numbered section scaffolding · emoji status · display fonts in UI · text overflow at any breakpoint · presenting invented data as live.

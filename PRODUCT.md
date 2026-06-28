# Product

## Register

product

## Users

Finance and operations staff at Malaysian SMEs — bookkeepers, finance managers, and owner-operators who handle cross-border payments. Their context is a focused, recurring task: at month-end (or whenever payments clear) they need to confirm that money received in the bank actually matches the invoices they issued and the payment proofs they were sent. They are not data scientists; they trust numbers, not jargon. Many work in daylight office conditions and read dense tables for long stretches.

The job to be done: **close the loop between three messy sources — bank statements, invoices, and payment proofs — quickly and with confidence**, surfacing the exceptions that need a human decision and clearing the rest automatically.

## Product Purpose

TreasuryFlow AI is an automated reconciliation platform. It ingests bank statements (CSV/XLSX), invoices (PDF/image), and payment proofs (PDF/image), parses them, and uses an AI matching engine to reconcile transactions to invoices across currencies — accounting for FX. Success is: the user uploads their documents, runs reconciliation, and trusts the result enough to act on it — matched items cleared, a short, legible list of exceptions to resolve, and an audit trail they could show an accountant or auditor.

It exists because cross-border reconciliation for SMEs is manual, error-prone, and slow, and because FX differences make naive matching fail.

## Brand Personality

Trustworthy, precise, calm. The voice is that of competent financial software: plain, exact, never theatrical. Three words: **dependable, exact, quiet**. Emotionally, the interface should make a non-expert feel *in control of their money* — reduced anxiety, earned confidence. The tool disappears into the task; the numbers are the hero, not the chrome.

## Anti-references

- **Sci-fi "hacker console" theater** — the prior build's "Morpheus Autonomous Reasoning Console", "neural network analyzing cross-border semantic variations", "INITIALIZE NODE", "SYSTEM INITIALIZED SUCCESSFULLY!". A treasury tool that cosplays as a movie hacking terminal erodes trust.
- **The hero-metric SaaS template** — three identical big-number/small-label cards with gradient icon badges across the top of every dashboard.
- **Emoji as status** (🟢 ⏳) and exclamation-mark copy.
- **Decoration over information** — fake/hardcoded charts presented as live data; uppercase tracked eyebrows on every section.

## Design Principles

1. **The numbers are the hero.** Chrome recedes; data, amounts, and match status get the visual weight. Tabular numerals, legible density, no ornament competing with figures.
2. **Earn trust through honesty.** Never present invented data as real. Show real states — empty, loading (skeleton), partial, error — truthfully. Copy states what happened, not what sounds impressive.
3. **Exceptions over noise.** The reconciliation result is mostly "fine"; the product's job is to make the *few things that need a human* obvious and to clear the rest quietly.
4. **One vocabulary everywhere.** The same button, the same status pill, the same table, the same field, screen to screen. Consistency is the trust signal; surprise is a bug.
5. **Calm under density.** Finance work is dense by nature. Handle density with rhythm, alignment, and restraint — not by hiding information or shouting it.

## Accessibility & Inclusion

WCAG 2.1 AA. Body and label text ≥4.5:1, large text ≥3:1; every semantic badge pair verified. Visible focus rings on all interactive elements; full keyboard navigation (nav, forms, tables, the activity drawer). Status is never conveyed by color alone — pair with icon and text. Every animation has a `prefers-reduced-motion: reduce` alternative. Both light and dark themes meet the same bar.

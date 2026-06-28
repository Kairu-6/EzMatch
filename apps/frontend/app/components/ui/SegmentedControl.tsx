"use client";

import React, { useRef } from "react";
import { cn } from "./cn";

export type SegmentItem = {
  value: string;
  label: string;
  count?: number;
};

/**
 * Accessible tab switcher for in-page content (statements / invoices / proofs).
 * Proper tablist semantics + roving focus with arrow keys. Active segment lifts
 * onto `surface` with a soft shadow and accent text — quiet, no color-as-status.
 *
 * Pair each tab with a panel that has `role="tabpanel"` and
 * `aria-labelledby={`seg-tab-${value}`}` for the relationship to be announced.
 */
export function SegmentedControl({
  items,
  value,
  onChange,
  className,
  "aria-label": ariaLabel,
}: {
  items: SegmentItem[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
  "aria-label"?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = (from: number, dir: -1 | 1) => {
    const next = (from + dir + items.length) % items.length;
    onChange(items[next].value);
    refs.current[next]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-center gap-1 p-1 rounded-lg bg-surface-2 border border-border",
        className,
      )}
    >
      {items.map((item, i) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            id={`seg-tab-${item.value}`}
            aria-selected={active}
            aria-controls={`seg-panel-${item.value}`}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(item.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                e.preventDefault();
                move(i, 1);
              } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                e.preventDefault();
                move(i, -1);
              }
            }}
            className={cn(
              "inline-flex items-center gap-2 h-8 px-3 rounded-md text-sm font-medium",
              "transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent",
              active
                ? "bg-surface text-accent-text shadow-sm"
                : "text-ink-muted hover:text-ink",
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span
                className={cn(
                  "tnum text-xs",
                  active ? "text-ink-muted" : "text-ink-subtle",
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

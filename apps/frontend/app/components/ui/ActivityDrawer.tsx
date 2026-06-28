"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChevronUp, Activity } from "lucide-react";
import { cn } from "./cn";

export type LogLevel = "info" | "success" | "warning" | "error" | "muted";
export type LogLine = { text: string; level?: LogLevel };

const levelClass: Record<LogLevel, string> = {
  info: "text-ink",
  success: "text-success-fg",
  warning: "text-warning-fg",
  error: "text-danger-fg",
  muted: "text-ink-subtle",
};

/**
 * The demoted "console": an honest, collapsible activity log. Collapsed to a
 * single status bar by default; expands to show the processing trail.
 */
export function ActivityDrawer({
  lines,
  running = false,
  title = "Activity log",
}: {
  lines: LogLine[];
  running?: boolean;
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const last = lines[lines.length - 1];

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines, open]);

  return (
    <div className="fixed bottom-0 left-0 right-0 lg:left-64 z-40 border-t border-border bg-surface-2/95 backdrop-blur-sm">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-3 px-4 sm:px-6 h-11 text-left outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset"
      >
        <span
          className={cn(
            "flex items-center gap-2 text-sm font-medium shrink-0",
            running ? "text-accent-text" : "text-ink-muted",
          )}
        >
          <Activity
            className={cn("w-4 h-4", running && "animate-pulse")}
            aria-hidden
          />
          {title}
        </span>
        <span className="flex-1 truncate text-sm text-ink-muted font-mono">
          {last ? last.text : "Idle"}
        </span>
        <ChevronUp
          className={cn(
            "w-4 h-4 text-ink-subtle transition-transform shrink-0",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      <div
        ref={scrollRef}
        className={cn(
          "overflow-y-auto font-mono text-xs px-4 sm:px-6 space-y-1 transition-[height] duration-200",
          open ? "h-40 py-3 border-t border-border" : "h-0",
        )}
      >
        {lines.length === 0 ? (
          <p className="text-ink-subtle">No activity yet.</p>
        ) : (
          lines.map((l, i) => (
            <p
              key={i}
              className={cn(
                levelClass[l.level ?? "muted"],
                i === lines.length - 1 && "font-medium",
              )}
            >
              {l.text}
            </p>
          ))
        )}
      </div>
    </div>
  );
}

import React from "react";
import { cn } from "./cn";

export function Skeleton({
  className,
}: {
  className?: string;
}) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-surface-2",
        className,
      )}
      aria-hidden
    />
  );
}

/** A few skeleton rows for table loading states. */
export function SkeletonRows({
  rows = 4,
  cols = 3,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <tbody>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r} className="border-b border-border last:border-0">
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c} className="px-4 py-3.5">
              <Skeleton className={cn("h-3.5", c === 0 ? "w-28" : "w-16")} />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

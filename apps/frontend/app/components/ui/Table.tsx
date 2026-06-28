import React from "react";
import { cn } from "./cn";

/** Horizontal-scroll wrapper so dense ledgers never break the layout. */
export function TableScroll({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("w-full overflow-x-auto", className)}>{children}</div>
  );
}

export function Table({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <table className={cn("w-full text-left border-collapse", className)}>
      {children}
    </table>
  );
}

export function Th({
  className,
  align = "left",
  children,
}: {
  className?: string;
  align?: "left" | "right" | "center";
  children?: React.ReactNode;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "sticky top-0 bg-surface-2 px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-ink-muted border-b border-border",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  className,
  align = "left",
  mono = false,
  children,
  colSpan,
}: {
  className?: string;
  align?: "left" | "right" | "center";
  mono?: boolean;
  children?: React.ReactNode;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={cn(
        "px-4 py-3 text-base text-ink align-middle",
        align === "right" && "text-right tnum",
        align === "center" && "text-center",
        mono && "font-mono text-sm",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function Tr({
  className,
  hover = false,
  children,
}: {
  className?: string;
  hover?: boolean;
  children: React.ReactNode;
}) {
  return (
    <tr
      className={cn(
        "border-b border-border last:border-0",
        hover && "hover:bg-surface-2/60 transition-colors",
        className,
      )}
    >
      {children}
    </tr>
  );
}

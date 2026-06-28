import React from "react";
import { cn } from "./cn";

export function Panel({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "bg-surface border border-border rounded-lg shadow-sm",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function PanelHeader({
  title,
  icon,
  action,
  className,
}: {
  title: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 px-4 py-3 border-b border-border",
        className,
      )}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        {icon && <span className="text-ink-subtle shrink-0">{icon}</span>}
        <h3 className="text-base font-semibold text-ink truncate">{title}</h3>
      </div>
      {action}
    </div>
  );
}

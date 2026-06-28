import React from "react";
import { cn } from "./cn";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center px-6 py-12 gap-3",
        className,
      )}
    >
      {icon && (
        <div className="flex items-center justify-center w-11 h-11 rounded-full bg-surface-2 text-ink-subtle">
          {icon}
        </div>
      )}
      <div className="space-y-1 max-w-sm">
        <p className="text-base font-medium text-ink">{title}</p>
        {description && (
          <p className="text-sm text-ink-muted leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

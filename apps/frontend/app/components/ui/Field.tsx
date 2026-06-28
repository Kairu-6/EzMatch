"use client";

import React, { useId } from "react";
import { cn } from "./cn";

export interface FieldProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
  icon?: React.ReactNode;
}

export function Field({
  label,
  hint,
  error,
  icon,
  className,
  id,
  ...props
}: FieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const describedBy = error
    ? `${fieldId}-error`
    : hint
      ? `${fieldId}-hint`
      : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={fieldId}
        className="text-sm font-medium text-ink"
      >
        {label}
      </label>
      <div className="relative">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle pointer-events-none">
            {icon}
          </span>
        )}
        <input
          id={fieldId}
          aria-invalid={!!error || undefined}
          aria-describedby={describedBy}
          className={cn(
            "w-full h-10 rounded-md bg-surface text-ink placeholder:text-ink-subtle",
            "border border-border-strong transition-colors",
            "outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30",
            icon ? "pl-9 pr-3" : "px-3",
            error && "border-danger focus-visible:border-danger focus-visible:ring-danger/30",
            className,
          )}
          {...props}
        />
      </div>
      {error ? (
        <p id={`${fieldId}-error`} className="text-sm text-danger-fg">
          {error}
        </p>
      ) : hint ? (
        <p id={`${fieldId}-hint`} className="text-sm text-ink-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

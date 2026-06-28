import React from "react";
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  XCircle,
  Info,
  type LucideIcon,
} from "lucide-react";
import { cn } from "./cn";

export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

const tones: Record<Tone, { cls: string; icon: LucideIcon }> = {
  success: {
    cls: "bg-success-subtle text-success-fg",
    icon: CheckCircle2,
  },
  warning: {
    cls: "bg-warning-subtle text-warning-fg",
    icon: Clock,
  },
  danger: {
    cls: "bg-danger-subtle text-danger-fg",
    icon: AlertTriangle,
  },
  info: {
    cls: "bg-info-subtle text-info-fg",
    icon: Info,
  },
  neutral: {
    cls: "bg-surface-2 text-ink-muted",
    icon: XCircle,
  },
};

export function StatusPill({
  tone,
  children,
  icon,
  className,
}: {
  tone: Tone;
  children: React.ReactNode;
  icon?: LucideIcon | null;
  className?: string;
}) {
  const cfg = tones[tone];
  const Icon = icon === null ? null : (icon ?? cfg.icon);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap",
        cfg.cls,
        className,
      )}
    >
      {Icon && <Icon className="w-3.5 h-3.5 shrink-0" aria-hidden />}
      {children}
    </span>
  );
}

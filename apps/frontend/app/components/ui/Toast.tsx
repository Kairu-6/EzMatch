"use client";

import React, { createContext, useContext, useCallback, useState } from "react";
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";
import { cn } from "./cn";

type ToastTone = "success" | "danger" | "info";
type ToastItem = { id: number; tone: ToastTone; title: string; description?: string };

const ToastContext = createContext<{
  toast: (t: Omit<ToastItem, "id">) => void;
}>({ toast: () => {} });

const icons = { success: CheckCircle2, danger: AlertTriangle, info: Info };
const accents: Record<ToastTone, string> = {
  success: "text-success-fg",
  danger: "text-danger-fg",
  info: "text-info-fg",
};

let counter = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (t: Omit<ToastItem, "id">) => {
      const id = ++counter;
      setItems((prev) => [...prev, { ...t, id }]);
      setTimeout(() => remove(id), 5000);
    },
    [remove],
  );

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-[min(360px,calc(100vw-2rem))]"
        role="region"
        aria-label="Notifications"
      >
        {items.map((t) => {
          const Icon = icons[t.tone];
          return (
            <div
              key={t.id}
              role="status"
              className="flex items-start gap-3 bg-surface border border-border rounded-md shadow-md px-4 py-3 animate-[toast-in_180ms_cubic-bezier(0.22,1,0.36,1)]"
            >
              <Icon className={cn("w-4.5 h-4.5 mt-0.5 shrink-0", accents[t.tone])} />
              <div className="min-w-0 flex-1">
                <p className="text-base font-medium text-ink">{t.title}</p>
                {t.description && (
                  <p className="text-sm text-ink-muted mt-0.5">{t.description}</p>
                )}
              </div>
              <button
                onClick={() => remove(t.id)}
                aria-label="Dismiss"
                className="text-ink-subtle hover:text-ink transition-colors rounded outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
      <style>{`@keyframes toast-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}`}</style>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

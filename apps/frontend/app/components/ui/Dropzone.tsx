"use client";

import React, { useRef, useState } from "react";
import { UploadCloud, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { cn } from "./cn";

export type UploadStatus = "idle" | "uploading" | "done" | "error";

export function Dropzone({
  accept,
  onFiles,
  status = "idle",
  title,
  hint,
  message,
  disabled,
}: {
  accept: string;
  onFiles: (files: FileList) => void;
  status?: UploadStatus;
  title: string;
  hint: string;
  message?: string;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const busy = status === "uploading" || disabled;

  const open = () => !busy && inputRef.current?.click();

  return (
    <div
      role="button"
      tabIndex={busy ? -1 : 0}
      aria-disabled={busy || undefined}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!busy && e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
      }}
      className={cn(
        "flex flex-col items-center justify-center text-center gap-3 rounded-lg border border-dashed px-6 py-10 transition-colors outline-none",
        "focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]",
        busy ? "cursor-default" : "cursor-pointer",
        dragging
          ? "border-accent bg-accent-subtle"
          : status === "error"
            ? "border-danger/50 bg-danger-subtle/40"
            : status === "done"
              ? "border-success/40 bg-success-subtle/30"
              : "border-border-strong bg-surface-2/40 hover:border-accent hover:bg-surface-2",
      )}
    >
      <span
        className={cn(
          "flex items-center justify-center w-11 h-11 rounded-full",
          status === "error"
            ? "bg-danger-subtle text-danger-fg"
            : status === "done"
              ? "bg-success-subtle text-success-fg"
              : "bg-surface text-accent-text border border-border",
        )}
      >
        {status === "uploading" ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : status === "done" ? (
          <CheckCircle2 className="w-5 h-5" />
        ) : status === "error" ? (
          <AlertTriangle className="w-5 h-5" />
        ) : (
          <UploadCloud className="w-5 h-5" />
        )}
      </span>

      <div className="space-y-1">
        <p className="text-base font-medium text-ink">
          {status === "uploading"
            ? "Uploading…"
            : message && status !== "idle"
              ? message
              : title}
        </p>
        <p className="text-sm text-ink-muted">{hint}</p>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => {
          if (e.target.files?.length) onFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

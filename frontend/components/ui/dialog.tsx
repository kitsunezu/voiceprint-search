"use client";

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
}

export function Dialog({ open, onClose, title, description, children, className }: DialogProps) {
  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4"
      aria-modal="true"
      role="dialog"
    >
      {/* Scrim */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Panel — slides up on mobile, zooms in on desktop */}
      <div
        className={cn(
          "relative z-10 w-full sm:max-w-sm",
          "rounded-t-2xl sm:rounded-2xl border border-border bg-card shadow-2xl",
          "animate-in fade-in slide-in-from-bottom-4 sm:zoom-in-95 duration-200",
          className
        )}
      >
        {(title || description) && (
          <div className="px-5 pt-5 pb-0">
            <div className="flex items-start justify-between gap-3">
              {title && <h2 className="text-base font-semibold leading-snug">{title}</h2>}
              <button
                onClick={onClose}
                className="shrink-0 p-1.5 -mt-1 -mr-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label="Close"
              >
                <X className="size-4" />
              </button>
            </div>
            {description && (
              <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{description}</p>
            )}
          </div>
        )}
        <div className="px-5 pt-4 pb-6">{children}</div>
      </div>
    </div>
  );
}

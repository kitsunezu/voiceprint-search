"use client";

import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

export interface ModelOption {
  id: string;
  label: string;
  backend: string;
  embedding_dim: number;
  loaded: boolean;
  available: boolean;
}

interface ModelSelectorProps {
  value: string;
  onChange: (modelId: string) => void;
  className?: string;
}

export function ModelSelector({ value, onChange, className }: ModelSelectorProps) {
  const t = useTranslations("models");
  const [models, setModels] = useState<ModelOption[]>([]);
  const [defaultModel, setDefaultModel] = useState("");

  useEffect(() => {
    fetch("/api/models")
      .then((r) => r.json())
      .then((data) => {
        setModels(data.models ?? []);
        setDefaultModel(data.default_model ?? "");
        if (!value && data.default_model) {
          onChange(data.default_model);
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (models.length <= 1) return null;

  return (
    <div className={cn("space-y-1.5", className)}>
      <label className="text-xs font-medium text-muted-foreground">{t("label")}</label>
      <div className="flex flex-wrap gap-2">
        {models.map((m) => (
          <button
            key={m.id}
            type="button"
            disabled={!m.available}
            title={!m.available ? t("requiresToken") : undefined}
            onClick={() => m.available && onChange(m.id)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors",
              !m.available
                ? "cursor-not-allowed border-border/40 bg-card/50 text-muted-foreground/40 opacity-50"
                : value === m.id
                ? "border-primary bg-primary/10 text-primary font-medium"
                : "border-border bg-card text-muted-foreground hover:text-foreground hover:border-foreground/30"
            )}
          >
            <span>{m.label}</span>
            <span className="text-[10px] opacity-60">{m.embedding_dim}d</span>
            {m.id === defaultModel && m.available && (
              <span className="ml-0.5 rounded bg-primary/20 px-1 py-px text-[9px] font-semibold text-primary leading-tight">
                {t("default")}
              </span>
            )}
            {!m.available && (
              <span className="ml-0.5 rounded bg-destructive/20 px-1 py-px text-[9px] font-semibold text-destructive leading-tight">
                {t("unavailable")}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

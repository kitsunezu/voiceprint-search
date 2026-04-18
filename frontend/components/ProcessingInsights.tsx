"use client";

import { useTranslations } from "next-intl";

type Props = {
  mode: "verify" | "search";
  elapsedSeconds?: number | null;
  strategy?: string | null;
};

export function ProcessingInsights({
  mode,
  elapsedSeconds,
  strategy,
}: Props) {
  const t = useTranslations("preprocess");

  if (elapsedSeconds == null) {
    return null;
  }

  const seconds = elapsedSeconds.toFixed(1);
  let key = mode === "search" ? "summary_search" : "summary_verify_full";
  if (mode === "verify" && strategy === "fast-return") {
    key = "summary_verify_fast_return";
  } else if (mode === "verify" && strategy === "fast-profile") {
    key = "summary_verify_fast_profile";
  }

  return <p className="text-sm text-muted-foreground">{t(key, { seconds })}</p>;
}
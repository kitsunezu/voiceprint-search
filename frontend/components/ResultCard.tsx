"use client";

import { useTranslations } from "next-intl";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type VerificationDecision = "same" | "different" | "inconclusive";

interface Props {
  score: number;
  decision?: VerificationDecision;
  isSameSpeaker?: boolean | null;
  sameThreshold?: number;
  differentThreshold?: number;
  speakerName?: string;
  rank?: number;
}

function scorePosition(score: number) {
  return Math.min(100, Math.max(0, ((score + 1) / 2) * 100));
}

export function ResultCard({
  score,
  decision,
  isSameSpeaker,
  sameThreshold,
  differentThreshold,
  speakerName,
  rank,
}: Props) {
  const t = useTranslations("result");
  const resolvedDecision =
    decision ??
    (isSameSpeaker == null ? undefined : isSameSpeaker ? "same" : "different");
  const position = scorePosition(score);
  const hasDecisionBand = sameThreshold != null && differentThreshold != null;

  const accentClass =
    resolvedDecision === "same"
      ? "text-success"
      : resolvedDecision === "different"
        ? "text-destructive"
        : resolvedDecision === "inconclusive"
          ? "text-amber-500"
          : "text-primary";

  const dotClass =
    resolvedDecision === "same"
      ? "bg-success"
      : resolvedDecision === "different"
        ? "bg-destructive"
        : resolvedDecision === "inconclusive"
          ? "bg-amber-500"
          : "bg-primary";

  return (
    <Card>
      <CardContent className="space-y-4 pt-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              {rank != null && <Badge variant="secondary">#{rank}</Badge>}
              {speakerName && <p className="truncate font-semibold">{speakerName}</p>}
            </div>
            <p className={cn("mt-1 text-3xl font-bold tabular-nums", accentClass)}>
              {score.toFixed(4)}
            </p>
            <p className="text-xs text-muted-foreground">{t("cosine")}</p>
          </div>

          {resolvedDecision && (
            <Badge variant="secondary" className={cn("shrink-0", accentClass)}>
              {t(`decision_${resolvedDecision}`)}
            </Badge>
          )}
        </div>

        <div className="space-y-2">
          <div className="relative h-2 rounded-full bg-muted">
            {hasDecisionBand && (
              <>
                <span
                  className="absolute inset-y-0 w-px bg-border"
                  style={{ left: `${scorePosition(differentThreshold)}%` }}
                />
                <span
                  className="absolute inset-y-0 w-px bg-border"
                  style={{ left: `${scorePosition(sameThreshold)}%` }}
                />
              </>
            )}
            <span
              className={cn(
                "absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-background",
                dotClass,
              )}
              style={{ left: `${position}%` }}
            />
          </div>

          {hasDecisionBand && (
            <p className="text-xs text-muted-foreground">
              {t("decision_rule", {
                different: differentThreshold.toFixed(2),
                same: sameThreshold.toFixed(2),
              })}
            </p>
          )}
        </div>

        <p className="text-xs text-muted-foreground">
          {resolvedDecision ? t("cosine_explanation") : t("search_score_note")}
        </p>
      </CardContent>
    </Card>
  );
}

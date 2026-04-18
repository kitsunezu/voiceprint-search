"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Props {
  score: number;
  probability: number;
  isSameSpeaker?: boolean;
  speakerName?: string;
  rank?: number;
}

const R = 38;
const CIRC = 2 * Math.PI * R;

export function ResultCard({
  score,
  probability,
  isSameSpeaker,
  speakerName,
  rank,
}: Props) {
  const t = useTranslations("result");
  const pct = probability * 100;

  // Trigger transition after mount so CSS animations actually play
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setReady(true), 60);
    return () => clearTimeout(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const strokeClass =
    probability >= 0.8
      ? "stroke-success"
      : probability >= 0.5
      ? "stroke-primary"
      : "stroke-destructive";

  const barClass =
    probability >= 0.8
      ? "bg-success"
      : probability >= 0.5
      ? "bg-primary"
      : "bg-destructive";

  const textClass =
    probability >= 0.8
      ? "text-success"
      : probability >= 0.5
      ? "text-primary"
      : "text-destructive";

  const gaugeOffset = ready ? CIRC - (pct / 100) * CIRC : CIRC;

  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center gap-4">
          {/* ── Circular gauge ───────────────────────── */}
          <div className="relative h-24 w-24 shrink-0">
            <svg className="-rotate-90 h-full w-full" viewBox="0 0 96 96">
              {/* Track */}
              <circle
                cx="48"
                cy="48"
                r={R}
                fill="none"
                strokeWidth="8"
                className="stroke-muted/25"
              />
              {/* Fill arc */}
              <circle
                cx="48"
                cy="48"
                r={R}
                fill="none"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={CIRC}
                style={{
                  strokeDashoffset: gaugeOffset,
                  transition: "stroke-dashoffset 0.75s cubic-bezier(0.34,1.2,0.64,1)",
                }}
                className={strokeClass}
              />
            </svg>
            {/* Percentage label (centred, un-rotated) */}
            <div className="absolute inset-0 flex items-center justify-center">
              <span className={cn("text-lg font-bold tabular-nums leading-none", textClass)}>
                {pct.toFixed(0)}%
              </span>
            </div>
          </div>

          {/* ── Right side ───────────────────────────── */}
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              {rank != null && <Badge variant="secondary">#{rank}</Badge>}
              {speakerName && (
                <p className="font-semibold text-base truncate">{speakerName}</p>
              )}
            </div>

            {/* Horizontal fill bar */}
            <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={cn("h-full rounded-full transition-[width] duration-700 ease-out", barClass)}
                style={{ width: ready ? `${pct.toFixed(1)}%` : "0%" }}
              />
            </div>

            <div className="flex gap-3 text-xs text-muted-foreground flex-wrap">
              <span>
                {t("cosine")}:{" "}
                <strong className="text-foreground">{score.toFixed(4)}</strong>
              </span>
              {isSameSpeaker != null && (
                <span
                  className={cn(
                    "font-medium",
                    isSameSpeaker ? "text-success" : "text-destructive",
                  )}
                >
                  ● {isSameSpeaker ? t("same_speaker") : t("different_speaker")}
                </span>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

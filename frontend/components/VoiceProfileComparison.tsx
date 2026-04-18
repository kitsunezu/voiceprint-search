"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type VoiceDimension = {
  key: string;
  audio_a: number;
  audio_b: number;
  difference: number;
  audio_a_value: number;
  audio_b_value: number;
  unit: string;
};

type VoiceProfile = {
  profile_similarity: number;
  summary: string;
  dimensions: VoiceDimension[];
};

type Props = {
  profile?: VoiceProfile | null;
};

const CHART_SIZE = 260;
const CHART_CENTER = CHART_SIZE / 2;
const CHART_RADIUS = 82;

function polarPoint(value: number, index: number, count: number) {
  const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / count);
  return {
    x: CHART_CENTER + Math.cos(angle) * CHART_RADIUS * value,
    y: CHART_CENTER + Math.sin(angle) * CHART_RADIUS * value,
  };
}

function polygonPath(values: number[]) {
  return values
    .map((value, index) => {
      const point = polarPoint(value, index, values.length);
      return `${point.x},${point.y}`;
    })
    .join(" ");
}

function formatValue(value: number, unit: string) {
  if (unit === "Hz") {
    return `${value.toFixed(0)} Hz`;
  }
  return `${Math.round(value * 100)}%`;
}

export function VoiceProfileComparison({ profile }: Props) {
  const t = useTranslations("result");

  if (!profile || profile.dimensions.length === 0) {
    return null;
  }

  const similarity = Math.round(profile.profile_similarity * 100);
  const valuesA = profile.dimensions.map((item) => item.audio_a);
  const valuesB = profile.dimensions.map((item) => item.audio_b);

  return (
    <Card>
      <CardHeader className="space-y-3 pb-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="text-base">{t("profile_title")}</CardTitle>
            <p className="text-sm text-muted-foreground">{t("profile_subtitle")}</p>
          </div>
          <Badge variant="secondary" className="text-sm tabular-nums">
            {t("profile_similarity")}: {similarity}%
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{t(`profile_summary_${profile.summary}`)}</p>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
        <div className="rounded-2xl border border-border/70 bg-muted/20 p-4">
          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-primary" />
              {t("profile_audio_a")}
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
              {t("profile_audio_b")}
            </span>
          </div>

          <svg viewBox={`0 0 ${CHART_SIZE} ${CHART_SIZE}`} className="mx-auto mt-4 h-[260px] w-full max-w-[260px] overflow-visible">
            {[0.2, 0.4, 0.6, 0.8, 1].map((level) => (
              <polygon
                key={level}
                points={polygonPath(profile.dimensions.map(() => level))}
                fill="none"
                stroke="currentColor"
                strokeOpacity="0.14"
                className="text-muted-foreground"
              />
            ))}

            {profile.dimensions.map((item, index) => {
              const axisPoint = polarPoint(1, index, profile.dimensions.length);
              const labelPoint = polarPoint(1.2, index, profile.dimensions.length);
              return (
                <g key={item.key}>
                  <line
                    x1={CHART_CENTER}
                    y1={CHART_CENTER}
                    x2={axisPoint.x}
                    y2={axisPoint.y}
                    stroke="currentColor"
                    strokeOpacity="0.18"
                    className="text-muted-foreground"
                  />
                  <text
                    x={labelPoint.x}
                    y={labelPoint.y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="fill-muted-foreground text-[10px] font-medium"
                  >
                    {t(`profile_dimension_${item.key}`)}
                  </text>
                </g>
              );
            })}

            <polygon
              points={polygonPath(valuesA)}
              fill="currentColor"
              fillOpacity="0.15"
              stroke="currentColor"
              strokeWidth="2"
              className="text-primary"
            />
            <polygon
              points={polygonPath(valuesB)}
              fill="currentColor"
              fillOpacity="0.14"
              stroke="currentColor"
              strokeWidth="2"
              className="text-emerald-500"
            />
          </svg>
        </div>

        <div className="space-y-3">
          {profile.dimensions.map((item) => {
            const closeness = Math.max(0, 100 - Math.round(item.difference * 100));
            return (
              <div key={item.key} className="rounded-xl border border-border/70 bg-card/70 p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-foreground">{t(`profile_dimension_${item.key}`)}</p>
                  <span className="text-xs text-muted-foreground">
                    {t("profile_delta")}: {closeness}%
                  </span>
                </div>

                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg bg-primary/10 px-3 py-2">
                    <p className="text-xs text-muted-foreground">{t("profile_audio_a")}</p>
                    <p className="mt-1 text-sm font-medium text-foreground">
                      {formatValue(item.audio_a_value, item.unit)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-emerald-500/10 px-3 py-2">
                    <p className="text-xs text-muted-foreground">{t("profile_audio_b")}</p>
                    <p className="mt-1 text-sm font-medium text-foreground">
                      {formatValue(item.audio_b_value, item.unit)}
                    </p>
                  </div>
                </div>

                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary/80"
                    style={{ width: `${closeness}%` }}
                  />
                </div>
              </div>
            );
          })}

          <p className="text-xs text-muted-foreground">{t("profile_note")}</p>
        </div>
      </CardContent>
    </Card>
  );
}
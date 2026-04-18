"use client";

import { useTranslations } from "next-intl";
import { Card, CardContent } from "@/components/ui/card";

type Props = {
  separateVocals: boolean;
  onSeparateVocalsChange: (value: boolean) => void;
  fixedNote?: string;
};

export function PreprocessControls({
  separateVocals,
  onSeparateVocalsChange,
}: Props) {
  const t = useTranslations("preprocess");

  return (
    <Card>
      <CardContent className="pt-4 pb-4">
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={separateVocals}
            onChange={(e) => onSeparateVocalsChange(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-border text-primary focus:ring-primary shrink-0"
          />
          <span className="space-y-0.5">
            <span className="block text-sm font-medium text-foreground">{t("separate_vocals")}</span>
            <span className="block text-xs text-muted-foreground">{t("separate_vocals_hint")}</span>
          </span>
        </label>
      </CardContent>
    </Card>
  );
}
"use client";

import { Globe } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

const LOCALES = [
  { code: "en", label: "EN" },
  { code: "zh-TW", label: "繁中" },
  { code: "zh-CN", label: "简中" },
  { code: "ja", label: "日本語" },
  { code: "ko", label: "한국어" },
];

export function LanguageSwitcher({ locale }: { locale: string }) {
  const router = useRouter();
  const [, startTransition] = useTransition();

  function onChange(code: string) {
    document.cookie = `NEXT_LOCALE=${code}; path=/; max-age=31536000`;
    startTransition(() => router.refresh());
  }

  return (
    <div className="flex items-center gap-1.5">
      <Globe className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden />
      <select
        value={locale}
        onChange={(e) => onChange(e.target.value)}
        className="text-sm bg-transparent border-none outline-none cursor-pointer text-foreground"
        aria-label="Select language"
      >
        {LOCALES.map((l) => (
          <option key={l.code} value={l.code} className="bg-background text-foreground">
            {l.label}
          </option>
        ))}
      </select>
    </div>
  );
}

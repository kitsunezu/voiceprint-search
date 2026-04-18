import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { buildPageMetadata } from "@/lib/site";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const t = await getTranslations({ locale, namespace: "search" });

  return buildPageMetadata({
    locale,
    title: t("title"),
    description: t("subtitle"),
    path: "/search",
  });
}

export default function SearchLayout({ children }: { children: React.ReactNode }) {
  return children;
}
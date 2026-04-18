import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { buildPageMetadata } from "@/lib/site";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const t = await getTranslations({ locale, namespace: "verify" });

  return buildPageMetadata({
    locale,
    title: t("title"),
    description: t("subtitle"),
    path: "/verify",
  });
}

export default function VerifyLayout({ children }: { children: React.ReactNode }) {
  return children;
}
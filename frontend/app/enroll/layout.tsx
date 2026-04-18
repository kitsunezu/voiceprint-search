import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { buildPageMetadata } from "@/lib/site";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const t = await getTranslations({ locale, namespace: "enroll" });

  return buildPageMetadata({
    locale,
    title: t("title"),
    description: t("subtitle"),
    path: "/enroll",
  });
}

export default function EnrollLayout({ children }: { children: React.ReactNode }) {
  return children;
}
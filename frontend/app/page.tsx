import type { Metadata } from "next";
import Image from "next/image";
import { getLocale, getTranslations } from "next-intl/server";
import Link from "next/link";
import { absoluteUrl, buildPageMetadata, siteConfig } from "@/lib/site";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const t = await getTranslations({ locale, namespace: "home" });

  return buildPageMetadata({
    locale,
    title: t("title"),
    description: t("subtitle"),
    path: "/",
    useAbsoluteTitle: true,
  });
}

export default async function HomePage() {
  const locale = await getLocale();
  const t = await getTranslations("home");

  const features = [
    { title: t("verify_title"), desc: t("verify_desc"), href: "/verify" },
    { title: t("search_title"), desc: t("search_desc"), href: "/search" },
    { title: t("enroll_title"), desc: t("enroll_desc"), href: "/enroll" },
  ];

  const summary = features.map((feature) => feature.desc).join(" ");
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: siteConfig.name,
      url: absoluteUrl("/"),
      logo: absoluteUrl(siteConfig.socialImage),
    },
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      name: t("title"),
      applicationCategory: "SecurityApplication",
      operatingSystem: "Web",
      description: t("subtitle"),
      url: absoluteUrl("/"),
      image: absoluteUrl(siteConfig.socialImage),
      inLanguage: locale,
      featureList: features.map((feature) => feature.title),
    },
  ];

  return (
    <div className="space-y-10 sm:space-y-12">
      <section className="relative overflow-hidden rounded-[2rem] border border-border bg-[radial-gradient(circle_at_top,_rgba(45,212,191,0.18),_transparent_55%),linear-gradient(135deg,_rgba(255,255,255,0.96),_rgba(241,245,249,0.9))] px-6 py-10 shadow-[0_24px_80px_-48px_rgba(8,47,73,0.55)] dark:bg-[radial-gradient(circle_at_top,_rgba(45,212,191,0.2),_transparent_52%),linear-gradient(135deg,_rgba(15,23,42,0.94),_rgba(9,15,27,0.92))] sm:px-10 sm:py-14">
        <div
          className="absolute inset-0 bg-[linear-gradient(120deg,_transparent,_rgba(20,184,166,0.08),_transparent)]"
          aria-hidden
        />
        <div className="relative mx-auto max-w-3xl text-center">
          <div className="mx-auto mb-6 flex h-28 w-28 items-center justify-center rounded-[1.75rem] border border-white/60 bg-white/80 p-4 shadow-lg shadow-cyan-500/10 backdrop-blur dark:border-white/10 dark:bg-card/80 sm:h-32 sm:w-32">
            <Image
              src="/voiceprint-logo.png"
              alt=""
              aria-hidden
              width={256}
              height={256}
              priority
              className="h-full w-full object-contain"
            />
          </div>
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">{t("title")}</h1>
          <p className="mx-auto mt-4 max-w-2xl text-base text-muted-foreground sm:text-lg">
            {t("subtitle")}
          </p>
          <p className="mx-auto mt-4 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base">
            {summary}
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href="/search"
              className="inline-flex items-center justify-center rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-sm transition-transform hover:-translate-y-0.5 hover:bg-primary/90"
            >
              {features[1].title}
            </Link>
            <Link
              href="/verify"
              className="inline-flex items-center justify-center rounded-full border border-border bg-card/80 px-6 py-3 text-sm font-semibold text-foreground backdrop-blur transition-colors hover:bg-accent"
            >
              {features[0].title}
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-6 sm:grid-cols-3">
        {features.map((feature, index) => (
          <Link
            key={feature.href}
            href={feature.href}
            className="group block rounded-2xl border border-border bg-card/70 p-6 shadow-sm transition-all hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg"
          >
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary/80">
              {String(index + 1).padStart(2, "0")}
            </p>
            <h2 className="mt-4 text-lg font-semibold">{feature.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{feature.desc}</p>
          </Link>
        ))}
      </section>

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
    </div>
  );
}

import { getTranslations } from "next-intl/server";
import Link from "next/link";

export default async function HomePage() {
  const t = await getTranslations("home");

  const features = [
    { title: t("verify_title"), desc: t("verify_desc"), href: "/verify" },
    { title: t("search_title"), desc: t("search_desc"), href: "/search" },
    { title: t("enroll_title"), desc: t("enroll_desc"), href: "/enroll" },
  ];

  return (
    <div className="space-y-12">
      <section className="text-center space-y-4 py-12">
        <h1 className="text-4xl font-bold tracking-tight">{t("title")}</h1>
        <p className="text-lg text-muted-foreground max-w-xl mx-auto">{t("subtitle")}</p>
      </section>
      <section className="grid gap-6 sm:grid-cols-3">
        {features.map((f) => (
          <Link
            key={f.href}
            href={f.href}
            className="block rounded-xl border border-border p-6 hover:border-primary hover:shadow-sm transition-all"
          >
            <h2 className="text-lg font-semibold mb-2">{f.title}</h2>
            <p className="text-sm text-muted-foreground">{f.desc}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}

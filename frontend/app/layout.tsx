import type { Metadata, Viewport } from "next";
import { getLocale, getMessages, getTranslations } from "next-intl/server";
import { Providers } from "@/components/providers";
import { Navbar } from "@/components/navbar";
import { OtelBrowserInit } from "@/components/OtelBrowserInit";
import { absoluteUrl, getBaseUrl, getOpenGraphLocale, siteConfig } from "@/lib/site";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0f172a" },
  ],
};

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const tHome = await getTranslations({ locale, namespace: "home" });
  const image = absoluteUrl(siteConfig.socialImage);

  return {
    metadataBase: new URL(getBaseUrl()),
    applicationName: siteConfig.name,
    title: {
      default: tHome("title"),
      template: `%s | ${siteConfig.name}`,
    },
    description: tHome("subtitle"),
    keywords: [...siteConfig.keywords],
    category: "technology",
    manifest: "/manifest.webmanifest",
    icons: {
      icon: [{ url: siteConfig.socialImage, sizes: "768x768", type: "image/png" }],
      apple: [{ url: siteConfig.socialImage, sizes: "768x768", type: "image/png" }],
      shortcut: [siteConfig.socialImage],
    },
    formatDetection: {
      telephone: false,
      address: false,
      email: false,
    },
    appleWebApp: {
      capable: true,
      title: siteConfig.name,
      statusBarStyle: "default",
    },
    openGraph: {
      title: tHome("title"),
      description: tHome("subtitle"),
      url: absoluteUrl("/"),
      siteName: siteConfig.name,
      type: "website",
      locale: getOpenGraphLocale(locale),
      images: [
        {
          url: image,
          width: 768,
          height: 768,
          alt: `${siteConfig.name} logo`,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: tHome("title"),
      description: tHome("subtitle"),
      images: [image],
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-image-preview": "large",
        "max-snippet": -1,
        "max-video-preview": -1,
      },
    },
  };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const messages = await getMessages();
  const tFooter = await getTranslations({ locale, namespace: "footer" });

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="min-h-screen flex flex-col bg-background text-foreground">
        <Providers locale={locale} messages={messages as Record<string, unknown>}>
          <OtelBrowserInit />
          <Navbar />
          <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">{children}</main>
          <footer className="border-t border-border px-6 py-4 text-center text-xs text-muted-foreground">
            {tFooter("brand")} &copy; {new Date().getFullYear()}
          </footer>
        </Providers>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { getLocale, getMessages } from "next-intl/server";
import { Providers } from "@/components/providers";
import { Navbar } from "@/components/navbar";
import { OtelBrowserInit } from "@/components/OtelBrowserInit";
import "./globals.css";

export const metadata: Metadata = {
  title: "Voiceprint Search",
  description: "Voice identification — verify and search speakers by voice",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="min-h-screen flex flex-col bg-background text-foreground">
        <Providers locale={locale} messages={messages as Record<string, unknown>}>
          <OtelBrowserInit />
          <Navbar />
          <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">{children}</main>
          <footer className="border-t border-border px-6 py-4 text-center text-xs text-muted-foreground">
            Voiceprint Search &copy; {new Date().getFullYear()}
          </footer>
        </Providers>
      </body>
    </html>
  );
}

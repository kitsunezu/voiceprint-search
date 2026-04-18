import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";

const locales = ["en", "zh-TW", "zh-CN", "ja", "ko"] as const;
type Locale = (typeof locales)[number];

function isValidLocale(locale: string): locale is Locale {
  return (locales as readonly string[]).includes(locale);
}

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get("NEXT_LOCALE")?.value;
  if (cookieLocale && isValidLocale(cookieLocale)) {
    return {
      locale: cookieLocale,
      timeZone: "UTC",
      messages: (await import(`../messages/${cookieLocale}.json`)).default,
    };
  }
  return {
    locale: "en",
    timeZone: "UTC",
    messages: (await import("../messages/en.json")).default,
  };
});

import type { Metadata } from "next";

const baseUrlFallback = "http://localhost:3010";

const openGraphLocaleMap = {
  en: "en_US",
  "zh-TW": "zh_TW",
  "zh-CN": "zh_CN",
  ja: "ja_JP",
  ko: "ko_KR",
} as const;

export const siteConfig = {
  name: "Voiceprint Search",
  shortName: "Voiceprint",
  description:
    "AI-powered voice identification platform for speaker verification, speaker search, and voice enrollment.",
  keywords: [
    "voiceprint search",
    "speaker verification",
    "speaker identification",
    "voice biometrics",
    "speaker search",
    "voice database",
    "voice enrollment",
  ],
  socialImage: "/voiceprint-logo.png",
} as const;

function normalizeConfiguredBaseUrl(value: string | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed) return baseUrlFallback;

  try {
    const parsed = trimmed.startsWith("http://") || trimmed.startsWith("https://")
      ? new URL(trimmed)
      : new URL(`https://${trimmed}`);
    parsed.pathname = "/";
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return baseUrlFallback;
  }
}

export function getBaseUrl(): string {
  return normalizeConfiguredBaseUrl(process.env.NEXT_PUBLIC_SITE_URL ?? process.env.SITE_URL);
}

export function absoluteUrl(path = "/"): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return new URL(normalizedPath, `${getBaseUrl()}/`).toString();
}

export function getOpenGraphLocale(locale: string): string {
  return openGraphLocaleMap[locale as keyof typeof openGraphLocaleMap] ?? openGraphLocaleMap.en;
}

type PageMetadataOptions = {
  locale: string;
  title: string;
  description: string;
  path: string;
  indexable?: boolean;
  useAbsoluteTitle?: boolean;
};

export function buildPageMetadata({
  locale,
  title,
  description,
  path,
  indexable = true,
  useAbsoluteTitle = false,
}: PageMetadataOptions): Metadata {
  const url = absoluteUrl(path);
  const image = absoluteUrl(siteConfig.socialImage);

  return {
    title: useAbsoluteTitle ? { absolute: title } : title,
    description,
    keywords: [...siteConfig.keywords],
    alternates: {
      canonical: url,
    },
    openGraph: {
      title,
      description,
      url,
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
      title,
      description,
      images: [image],
    },
    robots: indexable
      ? {
          index: true,
          follow: true,
          googleBot: {
            index: true,
            follow: true,
            "max-image-preview": "large",
            "max-snippet": -1,
            "max-video-preview": -1,
          },
        }
      : {
          index: false,
          follow: false,
          noarchive: true,
          googleBot: {
            index: false,
            follow: false,
            noimageindex: true,
          },
        },
  };
}
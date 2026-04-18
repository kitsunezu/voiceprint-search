import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/site";

const routes = [
  { path: "/", changeFrequency: "weekly" as const, priority: 1 },
  { path: "/verify", changeFrequency: "weekly" as const, priority: 0.8 },
  { path: "/search", changeFrequency: "weekly" as const, priority: 0.8 },
  { path: "/enroll", changeFrequency: "weekly" as const, priority: 0.7 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return routes.map((route) => ({
    url: absoluteUrl(route.path),
    lastModified,
    changeFrequency: route.changeFrequency,
    priority: route.priority,
  }));
}
import type { MetadataRoute } from "next";
import { siteConfig } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: siteConfig.name,
    short_name: siteConfig.shortName,
    description: siteConfig.description,
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#f5f7fb",
    theme_color: "#0f172a",
    icons: [
      {
        src: siteConfig.socialImage,
        sizes: "768x768",
        type: "image/png",
        purpose: "any",
      },
    ],
    shortcuts: [
      {
        name: "Speaker Search",
        short_name: "Search",
        url: "/search",
        description: "Find the closest speaker match from an uploaded audio clip.",
      },
      {
        name: "Speaker Verification",
        short_name: "Verify",
        url: "/verify",
        description: "Compare two audio clips to estimate whether they belong to the same speaker.",
      },
      {
        name: "Enroll Speaker",
        short_name: "Enroll",
        url: "/enroll",
        description: "Add a speaker and audio samples to the searchable voiceprint database.",
      },
    ],
  };
}
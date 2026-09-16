import type { NextConfig } from "next";

const publicApiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "");
const internalApiUrl = process.env.API_INTERNAL_URL?.replace(/\/+$/, "");

if (process.env.VERCEL === "1" && !publicApiUrl) {
  throw new Error(
    "NEXT_PUBLIC_API_URL must be configured for Vercel deployments",
  );
}

const config: NextConfig = {
  async rewrites() {
    const upstream =
      internalApiUrl ||
      (process.env.NODE_ENV === "development"
        ? "http://127.0.0.1:8000"
        : undefined);
    if (!upstream) return [];
    return [
      {
        source: "/api/v1/:path*",
        destination: `${upstream}/api/v1/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};
export default config;

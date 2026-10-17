import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  agentRules: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8020"}/api/:path*`,
      },
    ];
  },
  devIndicators: false,
};
export default config;

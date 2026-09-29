import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.join(__dirname),
  },
  serverExternalPackages: [
    "@aws-sdk/client-cloudwatch-logs",
    "@aws-sdk/client-sts",
    "@aws-sdk/client-xray",
  ],
};

export default nextConfig;

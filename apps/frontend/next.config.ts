import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* It goes right here at the root level instead of experimental! */
  allowedDevOrigins: ["192.168.56.1", "localhost:3000"]
};

export default nextConfig;
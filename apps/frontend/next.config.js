/** @type {import('next').NextConfig} */
const nextConfig = {
  /* It goes right here at the root level instead of experimental! */
  allowedDevOrigins: ["192.168.56.1", "localhost:3000"]
};

module.exports = nextConfig;
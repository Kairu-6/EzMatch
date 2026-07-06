/** @type {import('next').NextConfig} */
const nextConfig = {
  // Self-contained server bundle for the Docker image (copies only what runtime needs).
  output: "standalone",
  /* Origins allowed to hit the dev server (HMR/RSC). Include the Cloudflare
     tunnel so the app loads and hydrates when accessed through it. */
  allowedDevOrigins: [
    "192.168.56.1",
    "localhost:3000",
    "*.trycloudflare.com",
    "*.cfargotunnel.com",
  ],
};

module.exports = nextConfig;
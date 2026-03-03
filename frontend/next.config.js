/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Server-side rewrites: inside Docker the gateway is reachable at
    // http://gateway:8000, but the client bundle uses NEXT_PUBLIC_API_URL
    // which resolves to localhost:8000 (exposed port) for browser requests.
    const serverApiUrl =
      process.env.INTERNAL_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";
    return [
      {
        source: "/api/auth/:path*",
        destination: `${serverApiUrl}/api/auth/:path*`,
      },
      {
        source: "/api/dashboard/:path*",
        destination: `${serverApiUrl}/api/dashboard/:path*`,
      },
      {
        source: "/api/experiments/:path*",
        destination: `${serverApiUrl}/api/experiments/:path*`,
      },
      {
        source: "/api/xai/:path*",
        destination: `${serverApiUrl}/api/xai/:path*`,
      },
      {
        source: "/api/hitl/:path*",
        destination: `${serverApiUrl}/api/hitl/:path*`,
      },
      {
        source: "/api/guardrails/:path*",
        destination: `${serverApiUrl}/api/guardrails/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

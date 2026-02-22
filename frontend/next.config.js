/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Server-side rewrites: inside Docker the backend is reachable at
    // http://backend:8000, but the client bundle uses NEXT_PUBLIC_API_URL
    // which resolves to localhost:8000 (exposed port) for browser requests.
    const serverApiUrl =
      process.env.INTERNAL_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${serverApiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

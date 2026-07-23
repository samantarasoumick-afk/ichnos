import type { NextConfig } from "next";

// Where the Next.js server (not the browser) reaches the FastAPI
// backend to proxy /backend/* requests. Defaults to the same-host dev
// setup (both processes on localhost). In Docker Compose this is set
// to the backend service's container name (e.g. "http://backend:8000")
// since "127.0.0.1" inside the frontend container would otherwise
// mean "the frontend container itself," not the backend one.
const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${BACKEND_INTERNAL_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;

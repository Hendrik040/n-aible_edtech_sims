/** @type {import('next').NextConfig} */
// Build timestamp: 2025-10-06T00:00:00Z
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig

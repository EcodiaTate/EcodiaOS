// next.config.ts
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Let build pass even if ESLint has errors
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Let build pass even if TypeScript has errors
  typescript: {
    ignoreBuildErrors: true,
  },
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;

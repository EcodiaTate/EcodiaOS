// next.config.ts
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
  experimental: { typedRoutes: true },

  webpack: (config) => {
    config.module.rules.push({
      test: /\.(glsl|vs|fs|vert|frag)$/i,
      type: 'asset/source', // import as plain string
    });
    return config;
  },
};

export default nextConfig;

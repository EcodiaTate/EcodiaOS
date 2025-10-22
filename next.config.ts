// next.config.ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["three", "@react-three/fiber", "@react-three/drei"],
  webpack: (config) => {
    config.module.rules.push({
      test: /\.(glsl|vs|fs|vert|frag)$/i,
      exclude: /node_modules/,
      use: [
        { loader: "raw-loader" },       // makes file contents a JS string
        { loader: "glslify-loader" },   // applies glslify transforms/includes
      ],
    });
    return config;
  },
  experimental: { typedRoutes: true },
};

export default nextConfig;
